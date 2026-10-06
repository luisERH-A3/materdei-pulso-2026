"""O endereço da tela do chat dentro do SageMaker Studio: o do espaço do aluno, mais /proxy/8501/.

O JupyterLab do Studio repassa qualquer porta do espaço nesse caminho. Quem chama é o demo.sh.
"""
import json

import boto3

RESERVA = "No endereço desta aba do JupyterLab, troque tudo depois de /jupyterlab/default/ por proxy/8501/"

try:
    dados = json.load(open("/opt/ml/metadata/resource-metadata.json", encoding="utf-8"))
    espaco = boto3.client("sagemaker").describe_space(DomainId=dados["DomainId"], SpaceName=dados["SpaceName"])
    print(espaco["Url"].rstrip("/") + "/proxy/8501/")
except Exception:
    print(RESERVA)
