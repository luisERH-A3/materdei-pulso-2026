"""Lambda das ferramentas da agenda, publicada como alvo MCP do AgentCore Gateway.

O Gateway chama esta função com:
    event    = os argumentos da ferramenta, exatamente como no inputSchema
    context  = context.client_context.custom["bedrockAgentCoreToolName"] = "agenda___buscar_horarios"

As bases ficam num JSON no S3 (gerado a partir do Excel por data/prepare.py).
"""
import json
import os

import boto3

from rules import FERRAMENTAS

s3 = boto3.client("s3")
BUCKET = os.environ["DADOS_BUCKET"]
CHAVE = os.environ.get("DADOS_CHAVE", "bases/bases.json")


def _ler_bases() -> dict:
    return json.loads(s3.get_object(Bucket=BUCKET, Key=CHAVE)["Body"].read())


def _gravar_bases(bases: dict) -> None:
    s3.put_object(
        Bucket=BUCKET,
        Key=CHAVE,
        Body=json.dumps(bases, ensure_ascii=False, indent=1).encode("utf-8"),
        ContentType="application/json",
    )


def lambda_handler(event, context):
    nome_completo = context.client_context.custom["bedrockAgentCoreToolName"]
    nome = nome_completo.split("___", 1)[-1]  # tira o prefixo do alvo: "agenda___"

    if nome not in FERRAMENTAS:
        return {"erro": f"Ferramenta desconhecida: {nome}"}

    funcao, altera = FERRAMENTAS[nome]
    bases = _ler_bases()
    try:
        resultado = funcao(bases, event)
    except KeyError as erro:
        return {"erro": f"Parâmetro ou registro ausente: {erro}"}

    if altera and resultado.get("ok"):
        _gravar_bases(bases)
    # Log sem os argumentos: eles trazem dados do paciente (LGPD).
    print(json.dumps({"ferramenta": nome, "ok": resultado.get("ok", True)}))
    return resultado
