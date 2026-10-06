"""O agente da central de agendamento. É um agente só: não há supervisor nem subagentes.

    Agente = modelo + ferramentas + loop  (Módulo 3)

    cérebro       o modelo no Bedrock, com o guardrail na chamada     model.py
    instruções    o system prompt, do Bedrock Prompt Management       prompt.py
    mãos          cinco ferramentas: uma de RAG e quatro da agenda    tools/
    memória       AgentCore Memory, de curto prazo                    memory.py
    loop          pensar, agir, observar, repetir: quem roda é o Strands Agents, neste arquivo
"""
import asyncio
import re
import time
from contextlib import contextmanager

from opentelemetry import trace
from strands import Agent

from utils import config
from utils.trace import montar_rastro
from utils.logs import anotar, registro
from tools import ferramentas_do_agente
from memory import gerenciador_memoria
from model import modelo_conversa
from prompt import montar_prompt, prompt_publicado


def _sem_travessao(texto: str) -> str:
    """A regra de formato do prompt, garantida no código: travessão e meia-risca viram vírgula."""
    return re.sub(r"\s*[—–]\s*", ", ", texto)


async def _preparar(sessao_id: str, paciente_id: str, paciente_nome: str, versao_pedida: str, etapas: dict):
    """O que o agente precisa antes de chamar o modelo: as ferramentas, o system prompt e a conexão com a memória.

    As três buscas não dependem uma da outra, então rodam ao mesmo tempo: a espera é a da mais lenta, não a soma.
    """
    async def medir(nome: str, funcao, *argumentos):
        with _etapa(nome, etapas):
            return await asyncio.to_thread(funcao, *argumentos)

    relogio = time.perf_counter()
    ferramentas, (prompt, versao_do_prompt), memoria = await asyncio.gather(
        medir("ferramentas", ferramentas_do_agente),
        medir("buscar_prompt", montar_prompt, paciente_id, paciente_nome, versao_pedida),
        medir("abrir_memoria", gerenciador_memoria, sessao_id, paciente_id),
    )
    etapas["preparo_ms"] = _ms(relogio)
    return ferramentas, prompt, versao_do_prompt, memoria


async def _conversar(pergunta: str, sessao_id: str, paciente_id: str, paciente_nome: str, versao_pedida: str,
                     etapas: dict, modelo_id: str):
    """Roda o loop e emite eventos conforme acontecem: etapa (o que o agente está fazendo), texto (pedaço da
    resposta), ferramenta e, por último, fim."""
    yield {"tipo": "etapa", "nome": "preparo"}
    ferramentas, prompt, versao_do_prompt, memoria = await _preparar(sessao_id, paciente_id, paciente_nome, versao_pedida, etapas)
    try:
        with _etapa("ler_memoria", etapas):
            agente = Agent(
                model=modelo_conversa(modelo_id),   # cérebro: o modelo, com o guardrail na mesma chamada   (model.py)
                system_prompt=prompt,      # instruções: do Bedrock Prompt Management              (prompt.py)
                tools=ferramentas,         # mãos: as cinco ferramentas                            (tools/)
                session_manager=memoria,   # memória: AgentCore Memory                             (memory.py)
                callback_handler=None,  # sem eco no terminal: o rastro vai para a interface
                # observabilidade: o nome do agente e as etiquetas que aparecem em cada trace.
                # O session.id junta, no console, todos os traces da mesma conversa.
                name="central-de-agendamento",
                trace_attributes={"session.id": sessao_id, "user.id": paciente_id, "prompt.versao": versao_do_prompt},
            )
            mensagens_antes = len(agente.messages)  # o histórico que o Memory devolveu

        relogio = time.perf_counter()
        resultado = None
        loop = 0
        traces = []  # o que o guardrail avaliou em cada chamada ao modelo
        anunciadas = set()  # o pedido de ferramenta também chega aos pedaços: avisa só uma vez por pedido
        async for evento in agente.stream_async(pergunta):
            if evento.get("start_event_loop"):  # começa um loop: uma chamada ao modelo, com o guardrail junto
                loop += 1
                yield {"tipo": "etapa", "nome": "modelo", "loop": loop}
            elif "data" in evento:
                etapas.setdefault("primeiro_texto_ms", _ms(relogio))
                yield {"tipo": "texto", "texto": evento["data"]}
            elif "current_tool_use" in evento:
                pedido = evento["current_tool_use"]
                if pedido.get("name") and pedido.get("toolUseId") not in anunciadas:
                    anunciadas.add(pedido.get("toolUseId"))
                    yield {"tipo": "ferramenta", "nome": pedido["name"]}
            elif "result" in evento:
                resultado = evento["result"]
            elif "metadata" in evento.get("event", {}):  # o fim de cada chamada ao modelo traz o trace do guardrail
                trace = evento["event"]["metadata"].get("trace", {}).get("guardrail")
                if trace:
                    traces.append(trace)
        etapas["modelo_e_ferramentas_ms"] = _ms(relogio)
    finally:  # garante a gravação no Memory mesmo se a resposta for interrompida no meio
        await asyncio.to_thread(memoria.close)

    rastro = montar_rastro(agente, resultado, mensagens_antes, prompt, versao_do_prompt, modelo_id, traces)
    etapas["guardrail_ms"] = rastro["guardrail"]["tempo_ms"]  # já contado dentro de modelo_e_ferramentas_ms
    etapas["chamadas_ms"] = [volta["latencia_ms"] for volta in rastro["voltas"]]  # uma por chamada ao modelo
    rastro["etapas"] = etapas
    _anotar_guardrail(rastro["guardrail"])
    yield {"tipo": "fim", "resposta": _sem_travessao(str(resultado).strip()), "rastro": rastro}


def _ms(desde: float) -> int:
    return round((time.perf_counter() - desde) * 1000)


def _anotar_guardrail(guardrail: dict) -> None:
    """Deixa no trace o que o guardrail fez: um span com a situação no nome e os achados nos atributos."""
    entrada, saida = guardrail["entrada"], guardrail["saida"] or {"situacao": "não avaliou", "achados": []}
    with trace.get_tracer("pulso").start_as_current_span(f"guardrail: input {entrada['situacao']}, output {saida['situacao']}") as span:
        span.set_attribute("guardrail.entrada", entrada["situacao"])
        span.set_attribute("guardrail.saida", saida["situacao"])
        span.set_attribute("guardrail.achados", str(entrada["achados"] + saida["achados"]))
        span.set_attribute("guardrail.tempo_ms", guardrail["tempo_ms"])


@contextmanager
def _etapa(nome: str, etapas: dict):
    """Mede uma etapa e a registra como um span no trace (AgentCore Observability)."""
    relogio = time.perf_counter()
    with trace.get_tracer("pulso").start_as_current_span(nome):
        yield
    etapas[f"{nome}_ms"] = _ms(relogio)


async def responder(pergunta: str, sessao_id: str, paciente_id: str, paciente_nome: str = "", prompt_versao: str = ""):
    """Uma volta de conversa, em stream: monta o agente, roda o loop e emite os eventos.

    prompt_versao escolhe a versão do system prompt (vazio = a última publicada).
    O último evento é sempre {"tipo": "fim", "resposta": ..., "rastro": ...}.
    Cada resposta deixa uma linha no registro do Runtime (CloudWatch Logs), com o tempo de cada etapa (veja utils/logs.py).
    """
    inicio = time.perf_counter()
    etapas = {}
    usado = config.MODELO_CONVERSA  # o modelo que respondeu: muda se o de reserva assumir
    try:
        modelos = [config.MODELO_CONVERSA] + ([config.MODELO_RESERVA] if config.MODELO_RESERVA != config.MODELO_CONVERSA else [])
        primeiro_erro = None
        for tentativa, modelo_id in enumerate(modelos):
            emitiu_texto = False
            usado = modelo_id
            try:
                async for evento in _conversar(pergunta, sessao_id, paciente_id, paciente_nome, prompt_versao, etapas, modelo_id):
                    emitiu_texto = emitiu_texto or evento.get("tipo") == "texto"
                    yield evento
                break
            except Exception as erro:
                primeiro_erro = primeiro_erro or erro
                if emitiu_texto or tentativa == len(modelos) - 1:
                    raise primeiro_erro  # já começou a responder, ou não há outro modelo: não dá para trocar
                registro.exception("modelo %s falhou (sessão %s), tentando o de reserva %s", modelo_id, sessao_id, modelos[tentativa + 1])
                yield {"tipo": "etapa", "nome": "reserva", "modelo": modelos[tentativa + 1]}
    except Exception:
        registro.exception("erro ao responder (sessão %s, modelo %s, etapas %s)", sessao_id, usado, etapas)
        raise
    finally:
        anotar("resposta", sessao=sessao_id, modelo=usado, total_ms=_ms(inicio), **etapas)


async def aquecer() -> dict:
    """Deixa pronto o que só precisa ser feito uma vez por processo: a conexão com o Gateway, o texto do prompt
    e o cliente do modelo. A interface chama ao abrir uma conversa, e a primeira resposta não paga esse tempo.
    Não chama o modelo: não gasta tokens."""
    inicio = time.perf_counter()
    await asyncio.gather(
        asyncio.to_thread(ferramentas_do_agente),
        asyncio.to_thread(prompt_publicado),
        asyncio.to_thread(modelo_conversa, config.MODELO_CONVERSA),
    )
    anotar("aquecimento", total_ms=_ms(inicio))
    return {"tipo": "fim", "resposta": "", "aquecido_ms": _ms(inicio)}
