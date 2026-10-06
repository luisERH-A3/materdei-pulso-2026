"""O modo debug: o painel "Por dentro do agente", com uma peça do agente por aba.

    Resposta   onde foi o tempo e o caminho de cada resposta: o fluxograma e o loop, chamada a chamada
    Prompt     as instruções e as ferramentas que o modelo recebeu
    Memória    o que o AgentCore Memory guardou desta conversa
    Dados      a agenda do paciente no S3 e os documentos do RAG
    Vetores    os vetores do S3 Vectors num mapa 2D interativo                                 (vectors.py)
    Na AWS     links para ver cada recurso no console
"""
import html
import json

import streamlit as st

from client import (CONSOLE, LINK_DO_PROMPT, LINK_DOS_VETORES, agenda_no_s3, configuracao_da_memoria, conversas_do_paciente,
                    eventos_da_memoria, explicar_erro, link_do_guardrail, versoes_do_prompt)
from sheets import carregar_documentos
from style import curto, dica, duracao, etiquetas, icone, mostrar_json, titulo
from utils import config
from vectors import aba_vetores

CLASSES_GUARDRAIL = {"passou": "ok", "mascarou": "alerta", "bloqueou": "erro"}


def _preparo_ms(etapas: dict) -> int:
    """O tempo antes da primeira chamada ao modelo. As buscas rodam em paralelo: vale o relógio, não a soma."""
    buscas = etapas.get("preparo_ms", etapas.get("ferramentas_ms", 0) + etapas.get("buscar_prompt_ms", 0))
    return buscas + etapas.get("ler_memoria_ms", 0)


def tempos_da_resposta(rastro: dict, espera_ms: int | None) -> list[tuple[str, str, int]]:
    """Reparte a espera de uma resposta entre as etapas: (nome, classe, milissegundos).

    O guardrail roda dentro de cada chamada ao modelo: o Bedrock informa quanto ele levou, e aqui esse tempo sai
    do modelo. O que sobra da espera medida no navegador é rede, AgentCore Runtime e a gravação na memória.
    """
    etapas = rastro.get("etapas") or {}
    preparo = _preparo_ms(etapas)
    loop = etapas.get("modelo_e_ferramentas_ms", 0)
    guardrail = min(etapas.get("guardrail_ms", 0), loop)
    chamadas = sum(volta["latencia_ms"] or 0 for volta in rastro["voltas"])
    if not rastro["voltas"]:  # o guardrail barrou: o modelo nem rodou
        guardrail, chamadas = loop, loop
    partes = [
        ("Preparo", "preparo", preparo),
        ("Modelo", "modelo", max(chamadas - guardrail, 0)),
        ("Guardrail", "guardrail", guardrail),
        ("Ferramentas", "ferramenta", max(loop - chamadas, 0)),
    ]
    if espera_ms:
        partes.append(("Rede e Runtime", "rede", max(espera_ms - preparo - loop, 0)))
    return [parte for parte in partes if parte[2] > 0]


def barra_de_tempos(rastro: dict, espera_ms: int | None) -> str:
    """Onde foi o tempo: uma barra com um pedaço por etapa e, embaixo, cada chamada ao modelo."""
    partes = tempos_da_resposta(rastro, espera_ms)
    total = sum(ms for _, _, ms in partes) or 1
    barra = "".join(f'<span class="{classe}" style="flex-grow:{ms}" title="{nome}: {duracao(ms)}"></span>' for nome, classe, ms in partes)
    legenda = "".join(
        f'<span><i class="{classe}"></i>{nome} <b>{duracao(ms)}</b> {round(ms * 100 / total)}%</span>' for nome, classe, ms in partes
    )
    voltas = rastro["voltas"]
    maior = max((volta["latencia_ms"] or 0 for volta in voltas), default=0) or 1
    chamadas = "".join(
        f'<div class="chamada"><span>Chamada {numero}: '
        f'{html.escape(", ".join(c["ferramenta"].split("___")[-1] for c in volta["chamadas"]) or "escreve a resposta")}</span>'
        f'<div><span class="modelo" style="width:{(volta["latencia_ms"] or 0) * 100 / maior:.0f}%"></span></div>'
        f'<em>{duracao(volta["latencia_ms"])}</em></div>'
        for numero, volta in enumerate(voltas, start=1)
    )
    return (f'<div class="tempos"><div class="barra">{barra}</div><div class="legenda">{legenda}</div>'
            f'<div class="chamadas">{chamadas}</div></div>')


def etiquetas_do_rastro(rastro: dict, espera_ms: int | None = None) -> str:
    """O resumo de uma resposta em etiquetas: tempo, chamadas ao modelo, ferramentas, tokens e guardrail."""
    guardrail = rastro.get("guardrail") or {}
    tempo = duracao(espera_ms) if espera_ms else f"{rastro['tempo_s']:.1f} s".replace(".", ",")
    pontas = [v["situacao"] for v in (guardrail.get("entrada"), guardrail.get("saida")) if v]
    situacao = next((s for s in ("bloqueou", "mascarou") if s in pontas), pontas[0] if pontas else "desligado")
    selo = ("guardrail", f"guardrail {situacao}", CLASSES_GUARDRAIL.get(situacao, ""))
    if not rastro["voltas"]:  # barrado no input: o modelo não foi chamado
        return etiquetas([selo, ("relogio", tempo, "")])
    ferramentas = sum(len(volta["chamadas"]) for volta in rastro["voltas"])
    return etiquetas([
        ("relogio", tempo, ""),
        ("loop", f"{len(rastro['voltas'])} chamada(s) ao modelo", ""),
        ("ferramenta", f"{ferramentas} ferramenta(s)", ""),
        ("tokens", f"{rastro['uso'].get('totalTokens', 0):,} tokens".replace(",", "."), ""),
        selo,
    ])


def mostrar_chamada(chamada: dict, chave: str) -> None:
    """Uma ferramenta: o que o modelo pediu e o que o código devolveu."""
    argumentos = ", ".join(f"{nome}={valor!r}" for nome, valor in chamada["argumentos"].items())
    st.markdown("**Age** · o modelo pede, o código executa")
    st.code(f"{chamada['ferramenta']}({argumentos})", language="python", wrap_lines=True)
    st.markdown("**Observa** · o resultado volta para o modelo")
    resultado = chamada["resultado"]
    if chamada["ferramenta"] == "consultar_orientacoes" and isinstance(resultado, list):
        for trecho in resultado:  # RAG: os textos mais próximos da pergunta no S3 Vectors
            largura = max(0, min(100, round(trecho["similaridade"] * 100)))
            st.markdown(
                f'<div class="trecho"><b>{html.escape(trecho["titulo"])}</b> · similaridade {str(trecho["similaridade"]).replace(".", ",")}'
                f'<div class="barra" style="width:{largura}%"></div><small>{html.escape(trecho["trecho"])}</small></div>',
                unsafe_allow_html=True,
            )
    else:
        mostrar_json(resultado, chave)


def fluxograma(rastro: dict, pergunta: str) -> str:
    """O caminho desta resposta, de cima para baixo: paciente, guardrail, cada loop do modelo, guardrail, resposta.

    É montado a partir do rastro, então muda a cada pergunta. Ferramentas pedidas na mesmo loop ficam lado a lado.
    """
    guardrail = rastro.get("guardrail") or {}
    voltas = rastro["voltas"]
    interrompidas = rastro.get("voltas_interrompidas", 0)
    partes = []

    def no(classe: str, nome: str, detalhe: str = "", explicacao: str = "", marca: str = "", tempo: str = "") -> str:
        simbolo = ("guardrail" if nome.startswith("Guardrail") else "paciente" if nome == "Paciente" else
                   {"ponta": "resposta", "modelo": "modelo", "ferramenta": "ferramenta"}.get(classe, "preparo"))
        extra = f'<span class="marca">{html.escape(marca)}</span>' if marca else ""
        ajuda = dica(explicacao) if explicacao else ""
        relogio = f'<span class="tempo">{html.escape(tempo)}</span>' if tempo else ""
        linha = f"<small>{html.escape(detalhe)}</small>" if detalhe else ""
        return (f'<div class="no {classe}"><span class="bola">{icone(simbolo)}</span>'
                f'<span><b>{html.escape(nome)}</b>{extra}{ajuda}{relogio}</span>{linha}</div>')

    def liga(texto: str = "") -> None:
        partes.append(f'<div class="liga">{html.escape(texto)}</div>')

    def filtro(nome: str, verificacao: dict | None, explicacao: str, tempo: str = "") -> None:
        verificacao = verificacao or {"situacao": "desligado", "achados": []}
        achados = ", ".join(f"{a['protecao']}: {a['nome']}" for a in verificacao["achados"])
        classe = CLASSES_GUARDRAIL.get(verificacao["situacao"], "")
        partes.append(no(classe, f"Guardrail · {nome}", achados or "nada encontrado", explicacao, verificacao["situacao"], tempo))

    etapas = rastro.get("etapas") or {}
    preparo = [("ferramentas", "ferramentas_ms"), ("prompt", "buscar_prompt_ms"), ("abrir a memória", "abrir_memoria_ms"),
               ("ler a memória", "ler_memoria_ms")]
    partes.append(no("ponta", "Paciente", curto(pergunta, 90)))
    liga()
    if any(chave in etapas for _, chave in preparo):
        partes.append(no(
            "", "Preparar o agente", " · ".join(f"{nome} {duracao(etapas[chave])}" for nome, chave in preparo if chave in etapas),
            "Antes de chamar o modelo, o agente carrega as ferramentas, busca o system prompt no Prompt Management e abre a "
            "memória, tudo ao mesmo tempo. Depois lê a conversa guardada.", tempo=duracao(_preparo_ms(etapas)),
        ))
        liga()
    filtro("input", guardrail.get("entrada"),
           "O guardrail é um parâmetro a mais na chamada ao modelo. O Bedrock confere a mensagem do paciente antes de "
           "rodar o modelo. Se barrar, o modelo nem é chamado e a resposta é a mensagem padrão.")
    if not voltas:
        liga()
        partes.append(no("ponta", "Mensagem padrão", "o modelo não foi chamado. Na memória, a mensagem barrada vira um aviso"))
        return f'<div class="fluxo">{"".join(partes)}</div>'

    liga(f"system prompt {rastro['prompt_versao']} + {rastro['mensagens_da_memoria']} mensagem(ns) da memória")
    for numero, volta in enumerate(voltas, start=1):
        chamadas = volta["chamadas"]
        faz = f"pede {len(chamadas)} ferramenta(s)" if chamadas else "escreve a resposta"
        partes.append(no(
            "modelo", f"Modelo · loop {numero}", f"{rastro.get('modelo', '')} · {faz}",
            "Um loop é uma chamada ao modelo. Ele lê tudo o que há até aqui e decide: pedir ferramentas ou responder.",
            "tentativa interrompida" if numero <= interrompidas else "", duracao(volta["latencia_ms"]),
        ))
        if chamadas:
            liga("em paralelo" if len(chamadas) > 1 else "")
            ramos = []
            for chamada in chamadas:
                argumentos = ", ".join(f"{nome}={valor!r}" for nome, valor in chamada["argumentos"].items())
                ramos.append(no("ferramenta", chamada["ferramenta"], curto(argumentos, 70),
                                tempo=duracao(rastro.get("ferramentas_ms", {}).get(chamada["ferramenta"]))))
            partes.append(f'<div class="ramos">{"".join(ramos)}</div>')
            liga("resultado volta para o modelo")
        else:
            liga()
    filtro("output", guardrail.get("saida"),
           "Na mesma chamada, o Bedrock confere a resposta antes de ela sair. Aqui um dado sensível, como o CPF, "
           "é mascarado: o número nem chega à tela.",
           f"{duracao(guardrail.get('tempo_ms'))} no input + output" if guardrail.get("tempo_ms") is not None else "")
    liga()
    bloqueada = (guardrail.get("saida") or {}).get("situacao") == "bloqueou"
    total = _preparo_ms(etapas) + etapas.get("modelo_e_ferramentas_ms", 0)
    partes.append(no("ponta", "Mensagem padrão" if bloqueada else "Resposta ao paciente", tempo=duracao(total) if total else ""))
    return f'<div class="fluxo">{"".join(partes)}</div>'


def escolher_resposta() -> int | None:
    """Qual resposta do chat as abas Resposta e Prompt analisam. Devolve a posição dela nas mensagens."""
    mensagens = st.session_state.mensagens
    respostas = [i for i, mensagem in enumerate(mensagens) if mensagem.get("rastro")]
    if not respostas:
        return None

    def pergunta(i: int) -> str:
        texto = mensagens[i - 1]["texto"] if i else ""
        return f"{respostas.index(i) + 1}. {texto if len(texto) <= 60 else texto[:57] + '...'}"

    return st.selectbox("Resposta em análise", respostas, index=len(respostas) - 1, format_func=pergunta, label_visibility="collapsed")


def escolher_versao_do_prompt() -> None:
    """No Prompt Management não há versão ativa: a aplicação escolhe a versão a cada chamada. Aqui, quem escolhe é você."""
    try:
        versoes = versoes_do_prompt()
    except Exception as erro:
        st.warning("Não consegui listar as versões do prompt. " + explicar_erro(erro))
        return
    st.selectbox(
        "Versão do system prompt nas próximas respostas", [""] + versoes, key="prompt_versao",
        format_func=lambda v: f"versão {v}" if v else f"a última publicada (versão {versoes[0]})" if versoes else "a última publicada",
        help="No Bedrock Prompt Management as versões são cópias que não mudam, e nenhuma fica ativa: a aplicação diz qual "
             "quer a cada chamada. Troque aqui, envie a mesma pergunta e compare as respostas. Para criar uma versão, "
             "edite o rascunho no console e publique.",
    )


def aba_prompt(escolhida: int | None) -> None:
    titulo("O que o modelo recebeu",
           "Tudo o que o modelo sabe vem daqui: as instruções fixas (system prompt), o histórico que a memória devolve, a mensagem do paciente e a lista de ferramentas. Ele não tem acesso ao código nem aos dados.")
    escolher_versao_do_prompt()
    if escolhida is None:
        st.info("Envie uma mensagem para ver o que o modelo recebeu.")
        return
    mensagens = st.session_state.mensagens
    rastro = mensagens[escolhida]["rastro"]
    if not rastro["voltas"]:
        st.info("Nesta resposta o guardrail barrou o pedido no input: o modelo não recebeu nada.")
        return

    titulo("1. System prompt",
           "As instruções fixas, escritas por quem desenvolve: papel, regras e formato. É igual em toda conversa, "
           "só mudam os dados do paciente. O texto mora no Bedrock Prompt Management: para mudar, edite lá e crie uma "
           "versão. O agente passa a usar a versão nova em até um minuto, sem novo deploy.")
    st.caption(f"Versão {rastro['prompt_versao']}, publicada no [Bedrock Prompt Management]({LINK_DO_PROMPT}).")
    with st.expander("O texto que o modelo recebeu, com as variáveis já preenchidas", icon=":material/description:"):
        st.code(rastro["prompt"], language="xml")

    titulo("2. Histórico",
           "As mensagens anteriores desta conversa, devolvidas pelo AgentCore Memory. Sem elas, o modelo não saberia "
           "do que o paciente está falando.")
    st.caption(f"{rastro['mensagens_da_memoria']} mensagem(ns) de antes desta pergunta. O conteúdo está na aba Memória.")

    titulo("3. Prompt do usuário",
           "A mensagem do paciente, como ele escreveu. É a única parte que muda a cada pergunta, e a única que vem de "
           "fora: por isso passa antes pelo guardrail.")
    st.code(mensagens[escolhida - 1]["texto"], language="text", wrap_lines=True)

    titulo("4. Ferramentas",
           "O modelo nunca vê o código. Ele lê só o nome, a descrição e os parâmetros, e escolhe quando pedir cada uma. "
           "As usadas nesta resposta vêm primeiro, com a entrada que receberam e o que devolveram.")
    chamadas = [chamada for volta in rastro["voltas"] for chamada in volta["chamadas"]]
    usadas = {chamada["ferramenta"] for chamada in chamadas}
    for ferramenta in sorted(rastro["ferramentas"], key=lambda f: f["nome"] not in usadas):  # as usadas primeiro
        nome = ferramenta["nome"]
        vezes = [chamada for chamada in chamadas if chamada["ferramenta"] == nome]
        situacao = f"usada {len(vezes)}x nesta resposta" if vezes else "não usada"
        with st.expander(f"{nome} · {situacao}", expanded=bool(vezes), icon=":material/build:"):
            for numero, chamada in enumerate(vezes):
                mostrar_chamada(chamada, f"prompt-{escolhida}-{nome}-{numero}")
            st.markdown("**Descrição que o modelo lê**")
            st.caption(ferramenta["descricao"])
            mostrar_json(ferramenta["parametros"], f"ferramenta-{escolhida}-{nome}")


def linhas_da_conversa(eventos: list[dict]) -> tuple[list[tuple[str, str]], int]:
    """Traduz os eventos do Memory em linhas legíveis: (quem, o quê). Devolve também quantos são registros internos.

    Cada evento guarda uma mensagem do Strands em JSON. Os registros sem mensagem são o estado da sessão.
    """
    linhas, internos = [], 0
    itens = [item for evento in eventos for item in evento["payload"]]  # um evento pode trazer várias mensagens
    for item in itens:
        conversa = item.get("conversational")
        if not conversa:
            internos += 1
            continue
        try:
            blocos = json.loads(conversa["content"]["text"])["message"]["content"]
        except (KeyError, ValueError):
            continue
        papel = "agente" if conversa.get("role") == "ASSISTANT" else "paciente"
        for bloco in blocos:
            if "text" in bloco:
                linhas.append((papel, html.escape(curto(bloco["text"], 220)).replace("\n", "<br>")))
            elif "toolUse" in bloco:
                pedido = bloco["toolUse"]
                argumentos = ", ".join(f"{nome}={valor!r}" for nome, valor in pedido["input"].items())
                linhas.append(("agente", f"pede <code>{html.escape(pedido['name'])}({html.escape(curto(argumentos, 80))})</code>"))
            elif "toolResult" in bloco:
                texto = "".join(parte.get("text", "") for parte in bloco["toolResult"].get("content", []))
                linhas.append(("ferramenta", f"devolve <code>{html.escape(curto(texto, 110))}</code>"))
    return linhas, internos


def aba_memoria(paciente: dict) -> None:
    titulo("Memória do agente",
           "O modelo não lembra de nada entre uma mensagem e outra: cada chamada começa do zero. Quem guarda a conversa "
           "é o AgentCore Memory, um serviço fora do agente. Isso importa ainda mais aqui, onde cada sessão roda no AgentCore Runtime, "
           "em um ambiente isolado que é descartado.")
    try:
        configuracao = configuracao_da_memoria()
        versao = len(st.session_state.mensagens)
        eventos = eventos_da_memoria(paciente["paciente_id"], st.session_state.sessao, versao)
        conversas = conversas_do_paciente(paciente["paciente_id"], versao)
    except Exception as erro:
        st.warning("Não consegui ler a memória. " + explicar_erro(erro))
        return

    longa = bool(configuracao["estrategias"])
    st.markdown(
        '<div class="cartoes">'
        f'<div class="cartao ligada"><span class="estado">LIGADA</span><b>Curto prazo</b>'
        f'Guarda cada mensagem desta conversa, na ordem, por {configuracao["dias"]} dias. '
        'O agente relê tudo a cada pergunta.</div>'
        f'<div class="cartao {"ligada" if longa else "desligada"}"><span class="estado">{"LIGADA" if longa else "DESLIGADA"}</span>'
        '<b>Longo prazo</b>Extrairia fatos e preferências do paciente para usar em outras conversas. '
        'Fora do escopo, por LGPD.</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    linhas, internos = linhas_da_conversa(eventos)
    st.markdown(
        '<div class="numeros">'
        f'<span><b>{len(linhas)}</b>registros desta conversa{dica("Cada mensagem, pedido de ferramenta e resultado vira um registro. É essa lista que volta para o modelo a cada pergunta, e é por isso que ele entende a primeira opção ou essa consulta.")}</span>'
        f'<span><b>{conversas}</b>conversas guardadas deste paciente{dica("A memória curta é por conversa. Uma conversa nova não enxerga as anteriores: lembrar entre conversas é o papel da memória longa, que está desligada.")}</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    titulo("O que está guardado desta conversa",
           "Do mais antigo ao mais novo. Além das falas, ficam os pedidos de ferramenta e o que elas devolveram: "
           "assim o modelo não precisa consultar de novo o que já viu.")
    if not linhas:
        st.caption("Nada ainda. Envie uma mensagem no chat.")
        return
    st.markdown(
        "".join(
            f'<div class="linha"><span class="quem {quem}">{quem}</span><span class="fala">{oque}</span></div>'
            for quem, oque in linhas
        ),
        unsafe_allow_html=True,
    )
    st.caption(f"Mais {internos} registro(s) interno(s) do Strands, com o estado da sessão. Ator {paciente['paciente_id']}, {st.session_state.sessao}.")
    with st.expander("Como o Memory guarda (JSON)", icon=":material/data_object:"):
        mostrar_json(json.loads(json.dumps(eventos, default=str)), "memoria")


def aba_dados(paciente: dict) -> None:
    titulo("As fontes de informação",
           "A agenda são dados estruturados no S3, lidos e alterados pelas ferramentas. A base de conhecimento são textos, consultados por significado (RAG). O modelo nunca lê estes dados direto: só vê o que uma ferramenta devolve. Remarque uma consulta no chat e veja a tabela mudar.")
    st.caption(f"Agenda: s3://{config.DADOS_BUCKET}/{config.DADOS_CHAVE}")
    try:
        bases = agenda_no_s3(len(st.session_state.mensagens))
    except Exception as erro:
        st.warning("Não consegui ler a agenda. " + explicar_erro(erro))
    else:
        medicos = {m["medico_id"]: m for m in bases["medicos"]}

        def com_medico(linha: dict) -> dict:
            """Troca os ids pelo que se lê na tela: o nome do médico e a especialidade."""
            medico = medicos[linha["medico_id"]]
            visiveis = {coluna: valor for coluna, valor in linha.items() if coluna not in ("paciente_id", "medico_id")}
            if "livre" in visiveis:
                visiveis["livre"] = "sim" if visiveis["livre"] else "não"
            return {**visiveis, "médico": medico["nome"], "especialidade": medico["especialidade"]}

        with st.expander(f"Consultas de {paciente['nome']}", expanded=True, icon=":material/event:"):
            consultas = [com_medico(c) for c in bases["consultas"] if c["paciente_id"] == paciente["paciente_id"]]
            st.dataframe(consultas, hide_index=True)
        with st.expander("Grade de horários", icon=":material/calendar_month:"):
            st.dataframe([com_medico(h) for h in bases["horarios"]], hide_index=True)
    with st.expander("Base de conhecimento do RAG (S3 Vectors)", icon=":material/menu_book:"):
        st.markdown(
            f'<div class="titulo" style="font-weight:400;font-size:.85rem;opacity:.8">Cada texto virou um vetor de '
            f'{config.DIMENSAO_EMBEDDING} números com o {html.escape(config.MODELO_EMBEDDING)}, no índice '
            f'<b>{html.escape(config.VETORES_INDICE)}</b> do bucket <b>{html.escape(config.VETORES_BUCKET)}</b>.'
            + dica("Aqui o RAG é feito à mão, para a aula mostrar cada passo: gerar o embedding, gravar o vetor e buscar por "
                   "proximidade (app/agent/rag.py). Com muitos documentos, PDFs e textos longos, o caminho é o Bedrock "
                   "Knowledge Bases: ele divide os arquivos em pedaços, gera os embeddings, indexa e entrega a busca pronta. "
                   "O S3 Vectors continua servindo de armazenamento por baixo.")
            + "</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"[Ver no console do S3 Vectors]({LINK_DOS_VETORES}): na lista, abra o bucket e depois o índice.")
        st.dataframe(carregar_documentos(), hide_index=True)


def aba_aws() -> None:
    titulo("Os recursos na AWS",
           "Nada aqui é simulado: cada peça do agente é um recurso real na sua conta. Abra os links no console, com o mesmo login, e encontre lá os mesmos dados das outras abas.")
    projeto = config.DADOS_BUCKET.split("-dados-")[0] or "pulso"  # o prefixo dos recursos: pulso, aluno01...
    links = [
        ("Modelo de conversa", f"{CONSOLE}/bedrock/home?region={config.REGIAO}#/model-catalog",
         f"Amazon Bedrock · {config.MODELO_CONVERSA} (reserva: {config.MODELO_RESERVA})"),
        ("System prompt", LINK_DO_PROMPT,
         f"Bedrock Prompt Management · {config.PROMPT_ID or 'não configurado'} · o texto, as variáveis e as versões"),
        ("Guardrail", link_do_guardrail(),
         f"Bedrock Guardrails · {config.GUARDRAIL_ID or 'não configurado'}, versão {config.GUARDRAIL_VERSAO} · as regras e um painel de teste"),
        ("Memória", f"{CONSOLE}/bedrock-agentcore/memory?region={config.REGIAO}",
         f"AgentCore Memory · {config.MEMORIA_ID}"),
        ("Agenda", f"{CONSOLE}/s3/object/{config.DADOS_BUCKET}?region={config.REGIAO}&prefix={config.DADOS_CHAVE}",
         "Amazon S3 · o bases.json e as versões anteriores"),
        ("Vetores do RAG", LINK_DOS_VETORES,
         f"Amazon S3 Vectors · na lista, abra o bucket {config.VETORES_BUCKET} e o índice {config.VETORES_INDICE}"),
        ("Observabilidade", f"{CONSOLE}/cloudwatch/home?region={config.REGIAO}#gen-ai-observability/agent-core",
         "AgentCore Observability, no CloudWatch · sessões, traces e tokens de cada conversa"),
        ("Agente", f"{CONSOLE}/bedrock-agentcore/agents?region={config.REGIAO}",
         "AgentCore Runtime · onde o agente roda"),
        ("Ferramentas da agenda", f"{CONSOLE}/bedrock-agentcore/toolsAndGateways?region={config.REGIAO}",
         "AgentCore Gateway · a Lambda da agenda publicada como ferramentas MCP"),
        ("Recursos criados", f"{CONSOLE}/cloudformation/home?region={config.REGIAO}#/stacks?filteringText={projeto}",
         "AWS CloudFormation · a stack do projeto"),
    ]
    for nome, url, descricao in links:
        st.markdown(f"**[{nome}]({url})**  \n{descricao}")
    titulo("Esta conversa no Observability",
           "Cada mensagem vira um trace. A sessão junta os traces da mesma conversa. Dentro de um trace, os spans mostram, "
           "em ordem: ferramentas, buscar_prompt, ler_memoria, invoke_agent, com cada chamada ao modelo (chat) e cada "
           "ferramenta (execute_tool), e guardrail, que diz se ele passou, mascarou ou bloqueou. "
           "Os dados levam cerca de um minuto para aparecer.")
    st.markdown(f"No link Observabilidade, abra o agente **{projeto}_agente**, vá em **Sessions** e procure por:")
    st.code(st.session_state.sessao, language=None)


def aba_resposta(escolhida: int | None) -> None:
    """Uma resposta por dentro: onde foi o tempo, o fluxograma e, recolhido, o detalhe de cada chamada ao modelo."""
    if escolhida is None:
        st.info("Envie uma mensagem no chat para ver o caminho da resposta.", icon=":material/chat:")
        return
    mensagens = st.session_state.mensagens
    mensagem, pergunta = mensagens[escolhida], mensagens[escolhida - 1]["texto"]
    rastro, espera = mensagem["rastro"], mensagem.get("espera_ms")
    voltas, uso = rastro["voltas"], rastro["uso"]
    st.markdown(etiquetas_do_rastro(rastro, espera), unsafe_allow_html=True)

    titulo("Onde foi o tempo",
           "A espera do paciente, repartida. O guardrail roda dentro de cada chamada ao modelo, e aqui aparece separado. "
           "Rede e Runtime é o que sobra da espera medida no navegador: o caminho até o agente e a gravação na memória. "
           "Embaixo, cada chamada ao modelo: é ali que o tempo costuma variar. O mesmo registro fica nos logs do Runtime, no CloudWatch.")
    st.markdown(barra_de_tempos(rastro, espera), unsafe_allow_html=True)

    with st.expander("Fluxograma", icon=":material/account_tree:"):
        st.caption("Azul é o modelo, laranja é ferramenta, e a cor do guardrail mostra se ele passou, mascarou ou bloqueou.")
        st.markdown(fluxograma(rastro, pergunta), unsafe_allow_html=True)
    if mensagem.get("andamento"):
        with st.expander("O que o paciente viu enquanto esperava", icon=":material/hourglass_top:"):
            st.markdown(
                '<div class="andamento">' + "".join(
                    f'<div class="passo {passo["tipo"]}" style="opacity:1"><span class="bola">{icone("feito")}</span>'
                    f'<span>{html.escape(passo["texto"])}<span class="sub">{html.escape(passo["detalhe"])}</span></span>'
                    f'<small>{duracao(passo["ms"])}</small></div>' for passo in mensagem["andamento"]
                ) + "</div>",
                unsafe_allow_html=True,
            )
    if not voltas:
        return

    titulo("Passo a passo",
           "O agente é um loop: o modelo pensa, age (pede uma ferramenta), observa o resultado e repete, até poder "
           "responder. Abra uma chamada para ver o raciocínio, a ferramenta pedida, a entrada e o que ela devolveu.")
    interrompidas = rastro.get("voltas_interrompidas", 0)
    if interrompidas:
        st.caption(
            "Resposta retomada: a tela reiniciou no meio da primeira tentativa, e a pergunta foi enviada de novo. "
            "As chamadas marcadas como \"tentativa interrompida\" são da primeira."
        )
    for numero, volta in enumerate(voltas, start=1):
        papel = "pede " + ", ".join(c["ferramenta"].split("___")[-1] for c in volta["chamadas"]) if volta["chamadas"] else "responde"
        if numero <= interrompidas:
            papel += " · tentativa interrompida"
        simbolo = ":material/build:" if volta["chamadas"] else ":material/chat:"
        with st.expander(f"Chamada {numero} · {papel} · {duracao(volta['latencia_ms'])}", icon=simbolo):
            st.caption(f"{volta['uso'].get('inputTokens', 0)} tokens de input · {volta['uso'].get('outputTokens', 0)} de output")
            if volta["raciocinio"]:
                st.markdown("**Pensa**")
                st.caption(volta["raciocinio"])
            elif volta.get("raciocinio_oculto"):
                st.markdown("**Pensa**")
                st.caption("O modelo raciocinou, mas o Bedrock devolve esse raciocínio criptografado: só dá para ver o custo em tokens.")
            for indice, chamada in enumerate(volta["chamadas"]):
                mostrar_chamada(chamada, f"{escolhida}-{numero}-{indice}")
            if not volta["chamadas"]:
                st.markdown("**Responde** · não precisa de mais ferramentas, o loop termina")
    st.caption(
        f"Modelo {rastro.get('modelo', '')}. Tokens: {uso.get('inputTokens', 0)} de input, {uso.get('outputTokens', 0)} de output, "
        f"{uso.get('cacheReadInputTokens', 0)} lidos do cache."
        + (f" Guardrail na versão {config.GUARDRAIL_VERSAO}, [regras no console]({link_do_guardrail()})." if config.GUARDRAIL_ID else "")
    )


def painel_debug(paciente: dict) -> None:
    """O que acontece por trás do chat, com uma peça do agente por aba."""
    st.subheader("Por dentro do agente", anchor=False)
    escolhida = escolher_resposta()  # vale para as abas Resposta e Prompt
    resposta, prompt, memoria, dados, vetores, aws = st.tabs([
        ":material/route: Resposta", ":material/description: Prompt", ":material/history: Memória",
        ":material/table_chart: Dados", ":material/scatter_plot: Vetores", ":material/cloud: Na AWS",
    ])
    with resposta:
        aba_resposta(escolhida)
    with prompt:
        aba_prompt(escolhida)
    with memoria:
        aba_memoria(paciente)
    with dados:
        aba_dados(paciente)
    with vetores:
        aba_vetores()
    with aws:
        aba_aws()
