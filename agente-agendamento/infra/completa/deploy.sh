#!/usr/bin/env bash
# Demo completa: implanta (ou atualiza) todos os recursos na AWS. Quem chama é o demo.sh (bash agente-agendamento/demo.sh).
#
# Pré-requisitos: AWS CLI v2, uv e Python 3 (Linux, macOS ou WSL no Windows) e permissão para criar os recursos da stack.
#
#   1. cria o bucket de artefatos (se ainda não existir)
#   2. empacota o agente para arm64, com as dependências, como o Runtime exige
#   3. empacota a Lambda da agenda (só biblioteca padrão + o boto3 que já vem na Lambda)
#   4. sobe os dois .zip com um nome de versão novo, o que força a atualização
#   5. cria ou atualiza a stack do CloudFormation (infra/completa/template.yaml)
#   6. ativa os traces do agente no CloudWatch (uma vez por conta) e limita os logs a 3 dias
#   7. grava o .env com as saídas da stack
set -euo pipefail

PROJETO="${PROJETO:-pulso}"
REGIAO="${REGIAO:-us-east-1}"
# O modelo de conversa: o id usado na chamada (pode ser um perfil de inferência, us.*) e o id de base, para o IAM
MODELO_CONVERSA="${MODELO_CONVERSA:-us.openai.gpt-5.6-luna}"
MODELO_CONVERSA_BASE="${MODELO_CONVERSA_BASE:-${MODELO_CONVERSA#us.}}"
MODELO_RESERVA="${MODELO_RESERVA:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"  # assume se o principal falhar
MODELO_RESERVA_BASE="${MODELO_RESERVA_BASE:-${MODELO_RESERVA#us.}}"
CONTA="$(aws sts get-caller-identity --query Account --output text)"
ARTEFATOS="${PROJETO}-artefatos-${CONTA}-${REGIAO}"
VERSAO="$(date +%Y%m%d%H%M%S)"
BUILD="${BUILD:-$(pwd)/build}"  # onde os pacotes .zip são montados (no Studio, o demo.sh aponta para /tmp)

echo "== 1/7 Bucket de artefatos: ${ARTEFATOS}"
if ! aws s3api head-bucket --bucket "${ARTEFATOS}" >/dev/null 2>&1; then
  if [ "${REGIAO}" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "${ARTEFATOS}" --region "${REGIAO}"
  else
    aws s3api create-bucket --bucket "${ARTEFATOS}" --region "${REGIAO}" \
      --create-bucket-configuration LocationConstraint="${REGIAO}"
  fi
  aws s3api put-public-access-block --bucket "${ARTEFATOS}" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi
# Cada deploy sobe um .zip novo de ~47 MB; os antigos não servem mais e se acumulariam, então expiram em 3 dias
aws s3api put-bucket-lifecycle-configuration --bucket "${ARTEFATOS}" --lifecycle-configuration \
  '{"Rules":[{"ID":"expira-pacotes","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":3}}]}'

echo "== 2/7 Pacote do agente (arm64, Python 3.13)"
rm -rf "${BUILD}" && mkdir -p "${BUILD}/runtime"
uv pip install --quiet \
  --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary=:all: \
  --target "${BUILD}/runtime" -r app/agent/requirements.txt
cp app/agent/*.py "${BUILD}/runtime/"            # main.py fica na raiz do .zip, como o Runtime espera
cp -r app/agent/tools app/agent/utils "${BUILD}/runtime/"
python3 -c 'import shutil, sys; shutil.make_archive(sys.argv[1], "zip", sys.argv[1])' "${BUILD}/runtime"  # gera runtime.zip, sem depender do zip

echo "== 3/7 Pacote da Lambda da agenda"
mkdir -p "${BUILD}/agenda" && cp app/schedule/handler.py app/schedule/rules.py "${BUILD}/agenda/"
python3 -c 'import shutil, sys; shutil.make_archive(sys.argv[1], "zip", sys.argv[1])' "${BUILD}/agenda"

echo "== 4/7 Enviando os pacotes (versão ${VERSAO})"
aws s3 cp "${BUILD}/runtime.zip" "s3://${ARTEFATOS}/runtime-${VERSAO}.zip" --region "${REGIAO}"
aws s3 cp "${BUILD}/agenda.zip" "s3://${ARTEFATOS}/agenda-${VERSAO}.zip" --region "${REGIAO}"

echo "== 5/7 Stack ${PROJETO} (CloudFormation)"
aws cloudformation deploy \
  --stack-name "${PROJETO}" \
  --template-file infra/completa/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "${REGIAO}" \
  --parameter-overrides \
    Projeto="${PROJETO}" \
    ArtefatosBucket="${ARTEFATOS}" \
    RuntimeCodigoChave="runtime-${VERSAO}.zip" \
    LambdaCodigoChave="agenda-${VERSAO}.zip" \
    ModeloConversa="${MODELO_CONVERSA}" \
    ModeloConversaBase="${MODELO_CONVERSA_BASE}" \
    ModeloReserva="${MODELO_RESERVA}" \
    ModeloReservaBase="${MODELO_RESERVA_BASE}"

echo "== 6/7 Observabilidade: traces do agente no CloudWatch (Transaction Search)"
# Uma vez por conta. Sem isso, o Runtime não consegue enviar os traces e o painel do AgentCore Observability fica vazio.
if [ "$(aws xray get-trace-segment-destination --region "${REGIAO}" --query Destination --output text)" != "CloudWatchLogs" ]; then
  aws logs put-resource-policy --region "${REGIAO}" --policy-name TransactionSearchXRayAccess --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Sid\": \"TransactionSearchXRayAccess\", \"Effect\": \"Allow\",
      \"Principal\": {\"Service\": \"xray.amazonaws.com\"}, \"Action\": \"logs:PutLogEvents\",
      \"Resource\": [\"arn:aws:logs:${REGIAO}:${CONTA}:log-group:aws/spans:*\",
                     \"arn:aws:logs:${REGIAO}:${CONTA}:log-group:/aws/application-signals/data:*\"],
      \"Condition\": {\"ArnLike\": {\"aws:SourceArn\": \"arn:aws:xray:${REGIAO}:${CONTA}:*\"},
                      \"StringEquals\": {\"aws:SourceAccount\": \"${CONTA}\"}}
    }]}" >/dev/null
  aws xray update-trace-segment-destination --region "${REGIAO}" --destination CloudWatchLogs >/dev/null
fi
# Retenção curta (3 dias) nos logs e traces: é demo, e sem isso ficariam para sempre
RUNTIME_ID="$(aws cloudformation describe-stacks --stack-name "${PROJETO}" --region "${REGIAO}" \
  --query "Stacks[0].Outputs[?OutputKey=='RuntimeArn'].OutputValue" --output text)"
for GRUPO in "/aws/bedrock-agentcore/runtimes/${RUNTIME_ID##*/}-DEFAULT" "aws/spans" "/aws/application-signals/data"; do
  aws logs put-retention-policy --region "${REGIAO}" --retention-in-days 3 --log-group-name "${GRUPO}" 2>/dev/null || true
done

echo "== 7/7 Gravando o .env"
aws cloudformation describe-stacks --stack-name "${PROJETO}" --region "${REGIAO}" \
  --query "Stacks[0].Outputs" --output json | REGIAO="${REGIAO}" MODELO_CONVERSA="${MODELO_CONVERSA}" python3 -c '
import json, os, sys
saidas = {o["OutputKey"]: o["OutputValue"] for o in json.load(sys.stdin)}
env = {
    "REGIAO": os.environ["REGIAO"],
    "MODELO_CONVERSA": os.environ["MODELO_CONVERSA"],
    "DADOS_BUCKET": saidas["DadosBucket"],
    "VETORES_BUCKET": saidas["VetoresBucket"],
    "VETORES_INDICE": saidas["VetoresIndice"],
    "GATEWAY_URL": saidas["GatewayUrl"],
    "MEMORIA_ID": saidas["MemoriaId"],
    "GUARDRAIL_ID": saidas["ProtecaoId"],
    "GUARDRAIL_VERSAO": saidas["ProtecaoVersao"],
    "PROMPT_ID": saidas["PromptId"],
    "RUNTIME_ARN": saidas["RuntimeArn"],
}
open(".env", "w").write("".join(f"{k}={v}\n" for k, v in env.items()))
'

