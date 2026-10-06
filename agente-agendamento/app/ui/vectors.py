"""A aba Vetores do modo debug: os vetores do S3 Vectors num mapa 2D interativo, coloridos pela categoria."""
import html

import altair as alt
import numpy as np
import streamlit as st

from client import explicar_erro, vetores_do_rag
from style import titulo
from utils import config

TOP_NO_MAPA = 5  # quantos vizinhos da pergunta o mapa destaca
CORES_CATEGORIA = ["#2563eb", "#f97316", "#16a34a", "#9333ea", "#dc2626", "#0891b2", "#ca8a04", "#db2777"]


def _projetar_em_2d(vetores: list[list[float]]):
    """PCA: acha as duas direções em que os vetores mais variam e projeta cada um nelas.

    Devolve as coordenadas (n x 2), quanto da variação total cada eixo explica e uma função que põe
    qualquer outro vetor (a pergunta, por exemplo) no mesmo mapa.
    """
    matriz = np.array(vetores, dtype=float)
    centro = matriz.mean(axis=0)
    u, s, direcoes = np.linalg.svd(matriz - centro, full_matrices=False)
    variancia = s**2 / max((s**2).sum(), 1e-12)

    def projetar(vetor: list[float]) -> np.ndarray:
        return (np.array(vetor, dtype=float) - centro) @ direcoes[:2].T

    return u[:, :2] * s[:2], variancia[:2], projetar


@st.cache_data(show_spinner="Gerando o embedding da pergunta...")
def embedding_da_pergunta(pergunta: str) -> list[float]:
    """A pergunta vira um vetor com o mesmo modelo dos documentos: a mesma régua."""
    from rag import gerar_embeddings  # o mesmo código que o agente usa no RAG

    return gerar_embeddings([pergunta], tipo="search_query")[0]


def _similaridade(a: list[float], b: list[float]) -> float:
    """Similaridade de cosseno entre dois vetores: perto de 1 é parecido, perto de 0 não tem relação."""
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def aba_vetores() -> None:
    titulo("O mapa dos significados",
           f"Cada bolinha é um documento do RAG, guardado no S3 Vectors como um vetor de {config.DIMENSAO_EMBEDDING} números. Para caber na tela, os vetores foram reduzidos a 2 dimensões com PCA. Assuntos parecidos ficam perto: é essa proximidade que a busca usa.")
    if st.button("Recarregar do S3 Vectors"):
        vetores_do_rag.clear()
    try:
        vetores = vetores_do_rag()
    except Exception as erro:
        st.warning("Não consegui ler os vetores. " + explicar_erro(erro))
        return
    if len(vetores) < 3:
        st.info("O índice precisa de pelo menos 3 vetores para o mapa. Rode data/prepare.py para indexar a base.")
        return

    # A pergunta também vira ponto: é isso que a busca do RAG faz antes de procurar os vizinhos
    pergunta = st.text_input(
        "Onde uma pergunta cai no mapa?", key="pergunta_no_mapa", placeholder="posso tomar café antes do exame?",
        help="Escreva uma dúvida e tecle Enter. Ela vira um vetor com o mesmo modelo e aparece no mapa como um losango, "
             "com um raio até cada um dos 5 documentos mais próximos. "
             "Repare que a pergunta do café cai perto do jejum, sem ter a palavra jejum.",
    ).strip()
    vizinhos, vetor_da_pergunta = [], None
    if pergunta:
        try:
            vetor_da_pergunta = embedding_da_pergunta(pergunta)
        except Exception as erro:
            st.warning("Não consegui gerar o embedding da pergunta. " + explicar_erro(erro))
        else:
            vizinhos = sorted(
                ((_similaridade(vetor_da_pergunta, v["vetor"]), v) for v in vetores), key=lambda par: par[0], reverse=True
            )[:TOP_NO_MAPA]
    posicao = {v["doc_id"]: ordem for ordem, (_, v) in enumerate(vizinhos, start=1)}  # doc_id -> 1º, 2º, ...

    coordenadas, variancia, projetar = _projetar_em_2d([v["vetor"] for v in vetores])
    pontos = []
    for vetor, (x, y) in zip(vetores, coordenadas):
        texto = vetor.get("texto", "")
        inicio = ", ".join(f"{numero:.3f}" for numero in vetor["vetor"][:8])
        pontos.append({
            "doc_id": vetor["doc_id"],
            "título": vetor.get("titulo", ""),
            "categoria": vetor.get("categoria", "sem categoria"),
            "fonte": vetor.get("fonte", ""),
            "texto": texto if len(texto) <= 220 else texto[:217] + "...",
            "vetor": f"[{inicio}, ...] ({len(vetor['vetor'])} números)",
            "x": float(x),
            "y": float(y),
            "rotulo": f"{posicao[vetor['doc_id']]}º {vetor['doc_id']}" if vetor["doc_id"] in posicao else vetor["doc_id"],
            "opacidade": 0.9 if not posicao or vetor["doc_id"] in posicao else 0.3,  # com pergunta, só o top 5 fica forte
        })

    dados = alt.Data(values=pontos)
    eixo_x = alt.X("x:Q", title=f"componente 1 ({variancia[0]:.0%} da variação)", scale=alt.Scale(zero=False, padding=30))
    eixo_y = alt.Y("y:Q", title=f"componente 2 ({variancia[1]:.0%} da variação)", scale=alt.Scale(zero=False, padding=30))
    escolha = alt.selection_point(fields=["categoria"], bind="legend")  # clique na legenda para destacar uma categoria
    bolinhas = (
        alt.Chart(dados)
        .mark_circle(size=320, stroke="white", strokeWidth=1)
        .encode(
            x=eixo_x,
            y=eixo_y,
            color=alt.Color(
                "categoria:N",
                title="Categoria",
                scale=alt.Scale(range=CORES_CATEGORIA),  # cores bem diferentes: o tema do Streamlit usa tons parecidos
                legend=alt.Legend(orient="bottom", symbolOpacity=1),
            ),
            opacity=alt.condition(escolha, alt.Opacity("opacidade:Q", legend=None), alt.value(0.15)),
            tooltip=[alt.Tooltip(f"{campo}:N") for campo in ("doc_id", "título", "categoria", "fonte", "texto", "vetor")],
        )
        .add_params(escolha)
    )
    rotulos = alt.Chart(dados).mark_text(dy=-18, fontSize=11).encode(x=eixo_x, y=eixo_y, text="rotulo:N")
    camadas = bolinhas + rotulos

    if vizinhos:
        qx, qy = (float(c) for c in projetar(vetor_da_pergunta))
        raios = [
            {"x": qx, "y": qy, "x2": ponto["x"], "y2": ponto["y"], "ordem": posicao[ponto["doc_id"]]}
            for ponto in pontos if ponto["doc_id"] in posicao
        ]
        # raio cheio até os documentos que o agente recebe (RAG_TOP_K); pontilhado até os demais
        camadas += alt.Chart(alt.Data(values=raios)).mark_rule(strokeWidth=2.5, color="#111827", opacity=0.75).encode(
            x=eixo_x, y=eixo_y, x2="x2:Q", y2="y2:Q",
            strokeDash=alt.condition(alt.datum.ordem <= config.RAG_TOP_K, alt.value([1, 0]), alt.value([6, 5])),
        )
        camadas += alt.Chart(alt.Data(values=[p for p in pontos if p["doc_id"] in posicao])).mark_point(
            shape="circle", size=900, filled=False, stroke="#111827", strokeWidth=2.5,
        ).encode(x=eixo_x, y=eixo_y)
        ponto = alt.Data(values=[{"x": qx, "y": qy, "pergunta": pergunta}])
        camadas += alt.Chart(ponto).mark_point(shape="diamond", size=420, filled=True, color="#111827", stroke="white").encode(
            x=eixo_x, y=eixo_y, tooltip=[alt.Tooltip("pergunta:N")]
        )
        camadas += alt.Chart(ponto).mark_text(dy=22, fontSize=11, fontWeight="bold").encode(x=eixo_x, y=eixo_y, text=alt.value("a pergunta"))

    st.altair_chart(camadas.properties(height=520).interactive(), width="stretch")
    if vizinhos:
        st.markdown(
            "".join(
                f'<div class="trecho"><b>{ordem}º · {html.escape(v["doc_id"])} · {html.escape(v.get("titulo", ""))}</b> · similaridade '
                f'{f"{nota:.3f}".replace(".", ",")}<div class="barra" style="width:{max(0, min(100, round(nota * 100)))}%"></div></div>'
                for ordem, (nota, v) in enumerate(vizinhos, start=1)
            ),
            unsafe_allow_html=True,
        )
        st.caption(f"Os {TOP_NO_MAPA} documentos mais próximos da pergunta, medidos nas {config.DIMENSAO_EMBEDDING:,} dimensões".replace(",", ".") +
                   f". Raio cheio: os {config.RAG_TOP_K} que a ferramenta consultar_orientacoes devolve ao modelo. Raio pontilhado: os que ficaram logo atrás.")
    st.caption(
        "Passe o mouse numa bolinha para ver o documento e o começo do vetor. Role para dar zoom, arraste para mover, "
        "clique duas vezes para voltar e clique numa categoria da legenda para destacá-la. "
        f"Os dois eixos juntos mostram {variancia.sum():.0%} da variação: é uma aproximação, não a distância real."
    )
    with st.expander("Os vetores, um por linha"):
        st.dataframe(
            [{chave: ponto[chave] for chave in ("doc_id", "título", "categoria", "fonte", "vetor")} for ponto in pontos],
            hide_index=True,
        )
