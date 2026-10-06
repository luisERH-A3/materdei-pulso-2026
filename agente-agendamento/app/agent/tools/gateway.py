"""As ferramentas da agenda: chegam pelo AgentCore Gateway, pelo padrão MCP.

Quem executa é uma Lambda (app/schedule/), publicada pelo Gateway.
O agente as enxerga com o prefixo do alvo: agenda___buscar_consultas, agenda___remarcar_consulta...
"""
from threading import Lock

from utils import config
from utils.logs import registro

_gateway = None  # a conexão MCP com o Gateway, aberta na primeira mensagem e reaproveitada nas seguintes
_trava = Lock()  # o aquecimento e a primeira mensagem podem chegar juntos: só um deles abre a conexão


def _abrir_gateway():
    """Conexão MCP com o Gateway. A autenticação é IAM (SigV4): o papel do Runtime precisa de
    bedrock-agentcore:InvokeGateway. Nada de token ou segredo no código."""
    from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
    from strands.tools.mcp import MCPClient

    cliente = MCPClient(
        lambda: aws_iam_streamablehttp_client(
            endpoint=config.GATEWAY_URL,
            aws_region=config.REGIAO,
            aws_service="bedrock-agentcore",
        )
    )
    cliente.start()
    return cliente


def ferramentas_do_gateway() -> list:
    """As ferramentas da agenda, publicadas pelo Gateway. Abrir a conexão custa mais de 1 segundo, então ela
    fica aberta entre as mensagens. Se tiver caído (o Runtime ficou parado, por exemplo), abre outra."""
    global _gateway
    with _trava:
        try:
            if _gateway is None:
                _gateway = _abrir_gateway()
            return _gateway.list_tools_sync()
        except Exception:
            registro.warning("a conexão com o Gateway caiu: abrindo outra")
            _gateway = _abrir_gateway()
            return _gateway.list_tools_sync()
