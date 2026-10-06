"""O conhecimento do agente: RAG simples, com Cohere Embed v4 (embeddings) e Amazon S3 Vectors (busca).

Quem usa é a ferramenta consultar_orientacoes (tools/guidelines.py).

Estratégia: os documentos são curtos, então 1 documento = 1 vetor (sem divisão em pedaços).
    indexar(): título + texto -> embedding (search_document) -> S3 Vectors, com metadados
    buscar():  pergunta -> embedding (search_query) -> os k vizinhos mais próximos -> trechos
"""
import json
from functools import lru_cache

import boto3

from utils import config


@lru_cache
def _s3vectors():
    return boto3.client("s3vectors", region_name=config.REGIAO)


@lru_cache
def _bedrock():
    return boto3.client("bedrock-runtime", region_name=config.REGIAO)


def gerar_embeddings(textos: list[str], tipo: str = "search_document") -> list[list[float]]:
    """Transforma textos em vetores com o Cohere Embed v4.

    tipo = "search_document" para indexar a base, "search_query" para a pergunta do usuário.
    O Cohere usa os dois tipos de forma diferente, e isso melhora a busca.
    """
    vetores = []
    for i in range(0, len(textos), 96):  # até 96 textos por chamada
        corpo = {
            "texts": textos[i : i + 96],
            "input_type": tipo,
            "embedding_types": ["float"],
            "output_dimension": config.DIMENSAO_EMBEDDING,
        }
        resposta = _bedrock().invoke_model(
            modelId=config.MODELO_EMBEDDING,
            body=json.dumps(corpo),
            contentType="application/json",
            accept="application/json",
        )
        embeddings = json.loads(resposta["body"].read())["embeddings"]
        # Com embedding_types, a resposta vem por tipo: {"float": [[...], ...]}
        vetores.extend(embeddings["float"] if isinstance(embeddings, dict) else embeddings)
    return vetores


def indexar(documentos: list[dict]) -> int:
    """Grava (ou sobrescreve) um vetor por documento. A chave do vetor é o doc_id."""
    textos = [f"{d['titulo']}\n{d['texto']}" for d in documentos]
    vetores = gerar_embeddings(textos, tipo="search_document")
    itens = [
        {
            "key": d["doc_id"],
            "data": {"float32": v},
            # titulo e categoria são filtráveis; texto e fonte foram declarados como não filtráveis
            # no índice (infra/completa/template.yaml), porque só precisam voltar junto com o resultado.
            "metadata": {"titulo": d["titulo"], "categoria": d["categoria"], "texto": d["texto"], "fonte": d["fonte"]},
        }
        for d, v in zip(documentos, vetores)
    ]
    for i in range(0, len(itens), 100):
        _s3vectors().put_vectors(
            vectorBucketName=config.VETORES_BUCKET,
            indexName=config.VETORES_INDICE,
            vectors=itens[i : i + 100],
        )
    return len(itens)


def buscar(pergunta: str, k: int = config.RAG_TOP_K, categoria: str | None = None) -> list[dict]:
    """Busca por proximidade: devolve os k trechos mais parecidos com a pergunta.

    O S3 Vectors faz busca aproximada e às vezes devolve menos do que o topK pedido. Por isso pedimos 3 vezes mais
    candidatos e ficamos com os k melhores, que já vêm ordenados pela distância.
    """
    vetor = gerar_embeddings([pergunta], tipo="search_query")[0]
    parametros = {
        "vectorBucketName": config.VETORES_BUCKET,
        "indexName": config.VETORES_INDICE,
        "queryVector": {"float32": vetor},
        "topK": k * 3,
        "returnMetadata": True,  # exige s3vectors:GetVectors, além de s3vectors:QueryVectors
        "returnDistance": True,
    }
    if categoria:
        parametros["filter"] = {"categoria": categoria}
    resultado = _s3vectors().query_vectors(**parametros)
    return [
        {
            "titulo": v["metadata"]["titulo"],
            "trecho": v["metadata"]["texto"],
            "fonte": v["metadata"]["fonte"],
            "similaridade": round(1 - v["distance"], 3),  # distância de cosseno -> similaridade
        }
        for v in resultado["vectors"][:k]
    ]
