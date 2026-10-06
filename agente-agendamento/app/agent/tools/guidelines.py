"""Ferramenta local do agente: a busca na base de conhecimento (RAG).

O modelo nunca vê este código. Ele lê só o nome, os parâmetros e a docstring,
por isso a docstring diz quando usar e quando NÃO usar.

É a única ferramenta que roda sempre dentro do agente. As da agenda chegam pelo Gateway (gateway.py).
"""
from strands import tool

import rag


@tool
def consultar_orientacoes(pergunta: str) -> list[dict]:
    """Busca orientações oficiais da Rede: preparo de exames (jejum, água, roupa), documentos para levar,
    horários das unidades, regras de remarcação e faltas, convênio e resultados.
    Use antes de responder qualquer dúvida desse tipo. Não use para consultar a agenda do paciente.

    Args:
        pergunta: a dúvida do paciente em linguagem natural, por exemplo "glicemia precisa de jejum?".
    """
    return rag.buscar(pergunta)
