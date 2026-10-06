"""As mãos do agente: as cinco ferramentas que o modelo pode pedir.

    consultar_orientacoes   busca nos documentos da Rede (RAG)                        guidelines.py
    buscar_consultas        consultas do paciente                                     gateway.py
    buscar_horarios         horários livres de uma especialidade                      gateway.py
    buscar_exames           exames pedidos para o paciente                            gateway.py
    remarcar_consulta       altera a agenda, só com a confirmação do paciente         gateway.py

As quatro da agenda são uma Lambda (app/schedule/) publicada pelo AgentCore Gateway.
"""
from tools.gateway import ferramentas_do_gateway
from tools.guidelines import consultar_orientacoes


def ferramentas_do_agente() -> list:
    """A lista que o agente recebe: a busca nos documentos e as quatro ferramentas da agenda."""
    return [consultar_orientacoes, *ferramentas_do_gateway()]
