"""O acesso da interface ao agente e à AWS: a chamada ao agente, em stream, e as leituras do painel de debug.

Chama o agente publicado no AgentCore Runtime (RUNTIME_ARN no .env).
"""
import json
import threading

import boto3
import streamlit as st
from botocore.config import Config

from sheets import carregar_bases
from style import curto
from utils import config

CONSOLE = f"https://{config.REGIAO}.console.aws.amazon.com"
LINK_DO_PROMPT = f"{CONSOLE}/bedrock/home?region={config.REGIAO}#/prompt-management/{config.PROMPT_ID}"
# O console do S3 Vectors abre na lista de buckets de vetores: de lá, o bucket e o índice da demo
LINK_DOS_VETORES = f"{CONSOLE}/s3/vector-buckets?region={config.REGIAO}"


@st.cache_resource
def cliente(servico: str):
    # O agente pode ficar um bom tempo sem mandar nada, enquanto o modelo pensa: a leitura espera até 2 minutos
    return boto3.client(servico, region_name=config.REGIAO, config=Config(read_timeout=120))


@st.cache_data(show_spinner=False)
def _nome_do_guardrail() -> str:
    return cliente("bedrock").get_guardrail(guardrailIdentifier=config.GUARDRAIL_ID)["name"]


def link_do_guardrail() -> str:
    """A página do guardrail no console. O endereço leva o nome e o id, e o nome só o Bedrock sabe."""
    lista = f"{CONSOLE}/bedrock/home?region={config.REGIAO}#/guardrails"
    try:
        return f"{lista}/{_nome_do_guardrail()}/{config.GUARDRAIL_ID}"
    except Exception:  # sem o nome (login expirado, por exemplo), abre a lista. O erro não fica no cache
        return lista


@st.cache_data
def pacientes() -> list[dict]:
    return carregar_bases()["pacientes"]  # só para a lista de seleção; a agenda real está no S3


def _eventos(linhas):
    """Lê o stream do agente (SSE): cada linha "data: {...}" é um evento em JSON."""
    for linha in linhas:
        linha = linha.strip()
        if not linha.startswith(b"data:"):
            continue
        evento = json.loads(linha[5:])
        if not isinstance(evento, dict) or "tipo" not in evento:  # o Runtime manda os erros do agente como evento
            raise RuntimeError(evento.get("error", evento) if isinstance(evento, dict) else evento)
        yield evento


def _chamar(payload: dict, sessao: str, runtime=None):
    """Envia o payload ao agente e devolve as linhas do stream."""
    corpo = json.dumps(payload).encode("utf-8")
    resposta = (runtime or cliente("bedrock-agentcore")).invoke_agent_runtime(
        agentRuntimeArn=config.RUNTIME_ARN,
        runtimeSessionId=sessao,  # mesma sessão = mesma microVM e mesmo histórico no Memory
        payload=corpo,
        contentType="application/json",
        accept="text/event-stream",
    )
    yield from resposta["response"].iter_lines()


def perguntar(texto: str, paciente: dict, sessao: str, prompt_versao: str = ""):
    """Chama o agente e devolve os eventos conforme chegam: etapa, texto, ferramenta e, por último, fim."""
    payload = {"prompt": texto, "paciente_id": paciente["paciente_id"], "paciente_nome": paciente["nome"]}
    if prompt_versao:  # escolhida na aba Prompt; sem isso, vale a última publicada
        payload["prompt_versao"] = prompt_versao
    yield from _eventos(_chamar(payload, sessao))


def aquecer(sessao: str) -> None:
    """Avisa o agente de que uma conversa vai começar, sem esperar a resposta e sem chamar o modelo.

    No AgentCore Runtime, cada sessão nova sobe uma microVM e abre a conexão com o Gateway. Feito aqui, enquanto
    o paciente ainda está escrevendo, a primeira resposta não paga esse tempo.
    """
    runtime = cliente("bedrock-agentcore")  # criado aqui, fora da thread

    def em_segundo_plano() -> None:
        try:
            for _ in _chamar({"aquecer": True}, sessao, runtime):
                pass
        except Exception:  # é só uma otimização: se falhar, a primeira mensagem prepara tudo, como antes
            pass

    threading.Thread(target=em_segundo_plano, daemon=True).start()


# As leituras do painel de debug ficam em cache enquanto a conversa não anda (versao = número de mensagens).
# Assim abrir um item ou trocar de aba não consulta a AWS de novo, e a tela responde na hora.
@st.cache_data(ttl=120, show_spinner=False)
def eventos_da_memoria(paciente_id: str, sessao: str, versao: int) -> list[dict]:
    """O que o AgentCore Memory guardou desta sessão, do mais antigo ao mais novo."""
    resposta = cliente("bedrock-agentcore").list_events(
        memoryId=config.MEMORIA_ID,
        actorId=paciente_id,
        sessionId=sessao,
        includePayloads=True,
        maxResults=100,
    )
    return sorted(resposta["events"], key=lambda e: e["eventTimestamp"])


@st.cache_data(ttl=120, show_spinner=False)
def agenda_no_s3(versao: int) -> dict:
    objeto = cliente("s3").get_object(Bucket=config.DADOS_BUCKET, Key=config.DADOS_CHAVE)
    return json.loads(objeto["Body"].read())


@st.cache_data(show_spinner="Lendo os vetores no S3 Vectors...")
def vetores_do_rag() -> list[dict]:
    """Todos os vetores do índice, com os números (returnData) e os metadados de cada documento."""
    vetores, pagina = [], {}
    while True:
        resposta = cliente("s3vectors").list_vectors(
            vectorBucketName=config.VETORES_BUCKET,
            indexName=config.VETORES_INDICE,
            returnData=True,
            returnMetadata=True,
            **pagina,
        )
        vetores.extend(
            {"doc_id": v["key"], "vetor": v["data"]["float32"], **v.get("metadata", {})} for v in resposta["vectors"]
        )
        if not resposta.get("nextToken"):
            return sorted(vetores, key=lambda v: v["doc_id"])
        pagina = {"nextToken": resposta["nextToken"]}


@st.cache_data(ttl=60, show_spinner=False)
def versoes_do_prompt() -> list[str]:
    """As versões publicadas no Bedrock Prompt Management, da mais nova para a mais antiga."""
    paginas = cliente("bedrock-agent").get_paginator("list_prompts").paginate(promptIdentifier=config.PROMPT_ID)
    numeros = [p["version"] for pagina in paginas for p in pagina["promptSummaries"] if p["version"].isdigit()]
    return sorted(numeros, key=int, reverse=True)


@st.cache_data(ttl=300)
def configuracao_da_memoria() -> dict:
    """Como o AgentCore Memory do projeto está configurado: a validade dos eventos e as estratégias de longo prazo."""
    memoria = cliente("bedrock-agentcore-control").get_memory(memoryId=config.MEMORIA_ID)["memory"]
    return {
        "dias": memoria.get("eventExpiryDuration"),
        "estrategias": [estrategia.get("name", "") for estrategia in memoria.get("strategies", [])],
    }


@st.cache_data(ttl=120, show_spinner=False)
def conversas_do_paciente(paciente_id: str, versao: int) -> int:
    """Quantas conversas (sessões) deste paciente o Memory guarda. Cada uma é isolada das outras."""
    paginas = cliente("bedrock-agentcore").get_paginator("list_sessions").paginate(memoryId=config.MEMORIA_ID, actorId=paciente_id)
    return sum(len(pagina["sessionSummaries"]) for pagina in paginas)


def explicar_erro(erro: Exception) -> str:
    """Troca os erros mais comuns da aula por uma instrução do que fazer."""
    texto = str(erro)
    if any(pista in texto for pista in ("aws login", "xpired", "Unable to locate credentials", "InvalidClientTokenId")):
        cliente.clear()  # os próximos acessos criam clientes novos, já com o login refeito
        return "O login da AWS expirou. Rode `aws login` no terminal e tente de novo."
    if "ResourceNotFoundException" in texto and "InvokeAgentRuntime" in texto:  # a stack foi removida com o chat aberto
        return ("O agente desta implantação não existe mais: a stack foi removida. Pare o chat (Ctrl+C no terminal) e rode "
                "`bash agente-agendamento/demo.sh` para implantar de novo.")
    if "timed out" in texto:
        return ("O modelo demorou demais para responder e a chamada foi cancelada. Tente de novo. Se repetir, o modelo "
                "está lento no Bedrock: veja os logs do Runtime no CloudWatch e troque MODELO_CONVERSA no .env.")
    return f"Detalhe do erro: `{curto(texto, 300)}`"
