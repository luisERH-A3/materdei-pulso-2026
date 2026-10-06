"""O rastro de uma resposta: tudo o que aconteceu no loop, para a interface mostrar.

O Strands guarda a conversa como uma lista de mensagens. As mensagens novas de uma volta contam a história:
    assistant   o raciocínio do modelo, o texto e os pedidos de ferramenta (toolUse)
    user        os resultados das ferramentas (toolResult), que o seu código devolve ao modelo
"""
import json


def _texto_do_resultado(resultado: dict):
    """O resultado da ferramenta chega como texto. Se for JSON, devolve já convertido."""
    texto = "".join(bloco.get("text", "") for bloco in resultado.get("content", []))
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def montar_voltas(mensagens: list[dict]) -> list[dict]:
    """Uma volta = uma chamada ao modelo, com o que ele pensou, pediu e recebeu."""
    resultados = {
        bloco["toolResult"]["toolUseId"]: _texto_do_resultado(bloco["toolResult"])
        for mensagem in mensagens
        if mensagem["role"] == "user"
        for bloco in mensagem["content"]
        if "toolResult" in bloco
    }
    voltas = []
    for mensagem in mensagens:
        if mensagem["role"] != "assistant":
            continue
        volta = {"raciocinio": "", "raciocinio_oculto": False, "texto": "", "chamadas": []}
        for bloco in mensagem["content"]:
            if "reasoningContent" in bloco:
                conteudo = bloco["reasoningContent"]
                volta["raciocinio"] += conteudo.get("reasoningText", {}).get("text", "")
                volta["raciocinio_oculto"] = volta["raciocinio_oculto"] or "redactedContent" in conteudo  # o Luna criptografa
            elif "text" in bloco:
                volta["texto"] += bloco["text"]
            elif "toolUse" in bloco:
                pedido = bloco["toolUse"]
                volta["chamadas"].append({
                    "ferramenta": pedido["name"],
                    "argumentos": pedido["input"],
                    "resultado": resultados.get(pedido["toolUseId"]),
                })
        metadados = mensagem.get("metadata", {})
        volta["uso"] = metadados.get("usage", {})
        volta["latencia_ms"] = metadados.get("metrics", {}).get("latencyMs")
        voltas.append(volta)
    return voltas


# Como cada proteção aparece no trace do guardrail: (política, lista de achados, campo com o nome, rótulo)
_PROTECOES = [
    ("topicPolicy", "topics", "name", "tópico negado"),
    ("contentPolicy", "filters", "type", "filtro de conteúdo"),
    ("wordPolicy", "customWords", "match", "palavra bloqueada"),
    ("sensitiveInformationPolicy", "piiEntities", "type", "dado sensível"),
    ("sensitiveInformationPolicy", "regexes", "name", "dado sensível"),
]


def _situacao(avaliacoes: list[dict]) -> dict:
    """Resume as avaliações de uma ponta (entrada ou saída): passou, mascarou ou bloqueou, e o que foi encontrado."""
    achados = []
    for avaliacao in avaliacoes:
        for politica, lista, campo, rotulo in _PROTECOES:
            for item in avaliacao.get(politica, {}).get(lista, []):
                achado = {"protecao": rotulo, "nome": item[campo], "acao": item.get("action", "NONE")}
                if achado["acao"] != "NONE" and achado not in achados:
                    achados.append(achado)
    if any(achado["acao"] == "BLOCKED" for achado in achados):
        return {"situacao": "bloqueou", "achados": achados}
    return {"situacao": "mascarou" if achados else "passou", "achados": achados}


def resumir_guardrail(traces: list[dict]) -> dict:
    """O que o guardrail fez nesta resposta, a partir do trace que o Bedrock devolve em cada chamada ao modelo.

    Devolve {"entrada": ..., "saida": ..., "tempo_ms": ...}. Sem trace, o guardrail está desligado.
    """
    if not traces:
        desligado = {"situacao": "desligado", "achados": []}
        return {"entrada": desligado, "saida": desligado, "tempo_ms": 0}
    entradas = [avaliacao for trace in traces for avaliacao in trace.get("inputAssessment", {}).values()]
    saidas = [avaliacao for trace in traces for lista in trace.get("outputAssessments", {}).values() for avaliacao in lista]
    entrada = _situacao(entradas)
    tempo = sum(a.get("invocationMetrics", {}).get("guardrailProcessingLatency", 0) for a in entradas + saidas)
    return {"entrada": entrada, "saida": None if entrada["situacao"] == "bloqueou" else _situacao(saidas), "tempo_ms": tempo}


def _inicio_da_pergunta(historico: list[dict]) -> int:
    """Onde a pergunta atual começa no histórico da memória.

    Normalmente é no fim. Mas, se a resposta anterior foi interrompida (a tela reiniciou no meio), o histórico
    termina com uma pergunta sem resposta, e o modelo aproveita as ferramentas já chamadas nela.
    Nesse caso a pergunta começa naquela tentativa, para o rastro mostrar o caminho inteiro.
    """
    def tem(mensagem: dict, tipo: str) -> bool:
        return any(tipo in bloco for bloco in mensagem["content"])

    if not historico or (historico[-1]["role"] == "assistant" and not tem(historico[-1], "toolUse")):
        return len(historico)  # a última resposta terminou
    for posicao in range(len(historico) - 1, -1, -1):
        mensagem = historico[posicao]
        if mensagem["role"] == "user" and tem(mensagem, "text") and not tem(mensagem, "toolResult"):
            return posicao
    return len(historico)


def montar_rastro(agente, resultado, mensagens_antes: int, prompt: str, prompt_versao: str, modelo: str,
                  traces_do_guardrail: list[dict]) -> dict:
    """Junta o que a interface mostra: prompt, ferramentas, histórico, voltas, guardrail, tokens e tempo."""
    metricas = resultado.metrics
    guardrail = resumir_guardrail(traces_do_guardrail)
    barrado = guardrail["entrada"]["situacao"] == "bloqueou"  # o Bedrock nem chegou a chamar o modelo
    inicio = _inicio_da_pergunta(agente.messages[:mensagens_antes])
    interrompidas = len(montar_voltas(agente.messages[inicio:mensagens_antes]))
    return {
        "modelo": modelo,
        "prompt_versao": prompt_versao,
        "prompt": prompt,
        "ferramentas": [
            {"nome": spec["name"], "descricao": spec["description"], "parametros": spec["inputSchema"]["json"]}
            for spec in agente.tool_registry.get_all_tool_specs()
        ],
        "mensagens_da_memoria": inicio,  # o que o AgentCore Memory devolveu de antes desta pergunta
        "voltas": [] if barrado else montar_voltas(agente.messages[inicio:]),
        "voltas_interrompidas": 0 if barrado else interrompidas,  # voltas de uma tentativa anterior, retomada
        "guardrail": guardrail,
        "uso": dict(metricas.accumulated_usage),
        "tempo_s": round(sum(metricas.cycle_durations), 1),
        # quanto levou cada ferramenta (a média, se foi chamada mais de uma vez)
        "ferramentas_ms": {
            nome: round(m.total_time * 1000 / max(m.call_count, 1)) for nome, m in metricas.tool_metrics.items()
        },
    }
