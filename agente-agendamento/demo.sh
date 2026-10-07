#!/usr/bin/env bash
# A demo inteira em um comando. Rode da raiz do repositório, no terminal do JupyterLab (SageMaker Studio).
#
#   export PROJETO=alunomsouza                 o seu prefixo, só na primeira vez
#   bash agente-agendamento/demo.sh            implanta tudo na AWS, prepara os dados e sobe o chat
#   bash agente-agendamento/demo.sh abrir      só sobe o chat de novo (a demo já está implantada)
#   bash agente-agendamento/demo.sh remover    apaga da AWS tudo o que a demo criou
#
# Não há login nem instalação: o terminal já está ligado à conta, e o chat abre em outra aba do navegador.
#
# Opcional, antes do comando:  MODELO_CONVERSA=moonshotai.kimi-k2.5 (outro modelo do Bedrock)
set -euo pipefail
SCRIPT="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$SCRIPT")"

STUDIO=""  # no SageMaker Studio (JupyterLab): já vem logado, e a tela web abre pelo endereço do próprio Studio
[ -f /opt/ml/metadata/resource-metadata.json ] && STUDIO=1

# O prefixo fica guardado depois da primeira implantação: um terminal novo não precisa do export de novo
[ -z "${PROJETO:-}" ] && [ -f .projeto ] && PROJETO="$(cat .projeto)"
[ -n "$STUDIO" ] && [ -z "${PROJETO:-}" ] && [ "${1:-}" != ajuda ] && {
  printf '\nNão deu: falta o seu prefixo. Rode antes, trocando pelo seu:  export PROJETO=alunomsouza\n' >&2; exit 1; }
export PROJETO="${PROJETO:-pulso}"
export REGIAO="${REGIAO:-us-east-1}"
export MODELO_CONVERSA="${MODELO_CONVERSA:-us.openai.gpt-5.6-luna}"
export MODELO_RESERVA="${MODELO_RESERVA:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"  # assume se o principal falhar
export AWS_DEFAULT_REGION="${REGIAO}"
PY=.venv/bin/python
ENTRAR="Entre na AWS e tente de novo."
if [ -n "$STUDIO" ]; then
  ENTRAR="Recarregue a página."
  export PATH="$HOME/.local/bin:$PATH"    # onde o uv é instalado
  export UV_CACHE_DIR=/tmp/uv-cache       # os downloads ficam fora da pasta pessoal, que é pequena
  export BUILD=/tmp/pulso-build           # os pacotes .zip também
fi

avisar() { printf '\n== %s\n' "$*"; }
parar() { printf '\nNão deu: %s\n' "$*" >&2; exit 1; }

conferir() {
  command -v aws >/dev/null || parar "falta o AWS CLI v2."
  if ! command -v uv >/dev/null; then
    [ -n "$STUDIO" ] || parar "falta o uv. Instale com: curl -LsSf https://astral.sh/uv/install.sh | sh"
    avisar "Instalando o uv (só na primeira vez)"
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || parar "não consegui instalar o uv. Tente de novo."
  fi
  aws sts get-caller-identity >/dev/null 2>&1 || parar "você não está logado na AWS. ${ENTRAR}"
}

ambiente() {
  avisar "Ambiente Python (.venv)"
  [ -x "$PY" ] || uv venv --quiet --python 3.13 .venv
  uv pip install --quiet --python "$PY" -r requirements.txt
  # No Studio, o .venv vira um kernel do Jupyter: é o que o notebook do Módulo 2 usa
  [ -z "$STUDIO" ] || "$PY" -m ipykernel install --user --name pulso --display-name "Pulso (.venv)" >/dev/null
}

testar_modelo() {
  avisar "Testando o modelo ${MODELO_CONVERSA}"
  local erro="${TMPDIR:-/tmp}/demo-modelo.txt"
  aws bedrock-runtime converse --model-id "${MODELO_CONVERSA}" --inference-config maxTokens=32 \
    --messages '[{"role":"user","content":[{"text":"ok"}]}]' >/dev/null 2>"$erro" && return 0
  if grep -qE 'AccessDenied|ValidationException|ResourceNotFound' "$erro"; then  # erro da conta ou do id do modelo
    parar "a conta não consegue usar ${MODELO_CONVERSA}: $(tail -1 "$erro")
Tente outro modelo, por exemplo: MODELO_CONVERSA=moonshotai.kimi-k2.5 bash agente-agendamento/demo.sh"
  fi
  echo "Aviso: o Bedrock não respondeu agora ($(tail -1 "$erro" | cut -c1-120)). Seguindo: a implantação não depende disso."
}

testar_reserva() {  # só avisa: sem o modelo de reserva a demo roda, mas sem o fallback
  aws bedrock-runtime converse --model-id "${MODELO_RESERVA}" --inference-config maxTokens=16 \
    --messages '[{"role":"user","content":[{"text":"ok"}]}]' >/dev/null 2>"${TMPDIR:-/tmp}/demo-reserva.txt" \
    || echo "Aviso: o modelo de reserva ${MODELO_RESERVA} não responde ($(tail -1 "${TMPDIR:-/tmp}/demo-reserva.txt" | cut -c1-110)). A demo roda, mas sem o fallback."
}

implantar() {
  conferir
  ambiente
  testar_modelo
  testar_reserva
  bash infra/completa/deploy.sh
  avisar "Preparando os dados"
  "$PY" data/prepare.py
  echo "${PROJETO}" > .projeto
}

abrir() {
  [ -f .env ] || parar "a demo ainda não foi implantada. Rode: bash agente-agendamento/demo.sh"
  if [ -n "$STUDIO" ]; then  # o Studio publica a porta 8501 no próprio endereço, em /proxy/8501/
    avisar "Chat no ar. Abra em outra aba do navegador (para sair, Ctrl+C):"
    echo "   $("$PY" app/ui/proxy.py)"
    "$PY" -m streamlit run app/ui/app.py --browser.gatherUsageStats false --server.headless true \
      --server.port 8501 --server.enableCORS false --server.enableXsrfProtection false 2>&1 | grep -v -E 'URL:|can now view|^\s*$'
    return
  fi
  avisar "Abrindo o chat. Para sair, Ctrl+C"
  "$PY" -m streamlit run app/ui/app.py --browser.gatherUsageStats false
}

remover() {
  conferir
  CONTA="$(aws sts get-caller-identity --query Account --output text)"
  avisar "Removendo a stack ${PROJETO} da conta ${CONTA}"
  for BUCKET in "${PROJETO}-dados-${CONTA}-${REGIAO}" "${PROJETO}-artefatos-${CONTA}-${REGIAO}"; do
    aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1 || continue
    "$PY" -c "import boto3, sys; boto3.resource('s3').Bucket(sys.argv[1]).object_versions.delete()" "$BUCKET"  # com as versões
  done
  aws cloudformation delete-stack --stack-name "${PROJETO}"
  aws cloudformation wait stack-delete-complete --stack-name "${PROJETO}"
  aws s3api delete-bucket --bucket "${PROJETO}-artefatos-${CONTA}-${REGIAO}" 2>/dev/null || true  # fica fora da stack
  rm -f .env .projeto
  echo "Pronto. Nada da demo ficou na AWS."
}

case "${1:-}" in
  "") implantar && abrir ;;
  implantar) implantar ;;  # só implanta e prepara os dados, sem abrir o chat
  abrir) abrir ;;
  remover) remover ;;
  *) sed -n '2,11p' "$SCRIPT" | sed 's/^# \{0,1\}//' ;;
esac
