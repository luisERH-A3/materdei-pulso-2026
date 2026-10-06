"""Prepara os dados depois da implantação. Rode da raiz do repositório: agente-agendamento/.venv/bin/python agente-agendamento/data/prepare.py

    1. lê o Excel e confere se as bases se conectam
    2. sobe as bases estruturadas para o S3 (bases.json), onde as ferramentas da agenda leem e gravam.
       Se as datas do Excel já passaram, avança tudo em semanas inteiras, para a agenda nunca ficar vencida
    3. indexa a base de conhecimento no S3 Vectors (RAG)
    4. faz uma chamada de teste a cada modelo (no primeiro uso, isso ativa o modelo na conta)

Usa as credenciais de quem roda. Rode de novo para desfazer as remarcações feitas no chat.
"""
import json
import sys
import time
from pathlib import Path

import boto3

# Reaproveita o código do agente (modelos, RAG, config) e o leitor das planilhas
RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "app" / "agent"), str(RAIZ / "data")]

import rag  # noqa: E402
from utils import config  # noqa: E402
from model import testar_modelo_conversa  # noqa: E402
from rag import gerar_embeddings  # noqa: E402
from sheets import carregar_bases, carregar_documentos, manter_no_futuro, validar_conexoes  # noqa: E402


def main() -> None:
    if not (config.DADOS_BUCKET and config.VETORES_BUCKET):
        sys.exit("Faltam DADOS_BUCKET e VETORES_BUCKET no .env. Rode antes infra/completa/deploy.sh.")

    print("1/4 Lendo o Excel e conferindo as conexões entre as bases...")
    bases = carregar_bases()
    problemas = validar_conexoes(bases)
    if problemas:
        sys.exit("Bases inconsistentes:\n  " + "\n  ".join(problemas))
    print("    " + ", ".join(f"{nome}: {len(linhas)}" for nome, linhas in bases.items()))
    semanas = manter_no_futuro(bases)
    if semanas:
        print(f"    a agenda do Excel já passou: todas as datas avançaram {semanas} semana(s), nos mesmos dias da semana")

    print(f"2/4 Subindo as bases para s3://{config.DADOS_BUCKET}/{config.DADOS_CHAVE} ...")
    boto3.client("s3", region_name=config.REGIAO).put_object(
        Bucket=config.DADOS_BUCKET,
        Key=config.DADOS_CHAVE,
        Body=json.dumps(bases, ensure_ascii=False, indent=1).encode("utf-8"),
        ContentType="application/json",
    )

    print(f"3/4 Indexando a base de conhecimento no S3 Vectors ({config.VETORES_INDICE})...")
    total = rag.indexar(carregar_documentos())
    print(f"    {total} documentos indexados, {config.DIMENSAO_EMBEDDING} dimensões cada")
    for _ in range(6):  # num índice recém-criado, os vetores levam alguns segundos para aparecer na busca
        achados = rag.buscar("glicemia precisa de jejum?", k=1)
        if achados:
            break
        time.sleep(5)
    if achados:
        print(f"    teste de busca: '{achados[0]['titulo']}' (similaridade {achados[0]['similaridade']})")
    else:
        print("    teste de busca: ainda sem resultado. Rode o script de novo em um minuto.")

    print("4/4 Testando os modelos...")
    print(f"    {config.MODELO_EMBEDDING}: vetor com {len(gerar_embeddings(['teste'], 'search_query')[0])} posições")
    print(f"    {config.MODELO_CONVERSA}: {testar_modelo_conversa()!r}")
    print("Pronto. Para abrir o chat: bash agente-agendamento/demo.sh abrir")


if __name__ == "__main__":
    main()
