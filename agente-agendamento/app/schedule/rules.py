"""Regras de negócio das ferramentas da agenda (Módulo 3: ferramentas).

Roda dentro da Lambda que o AgentCore Gateway publica como ferramentas MCP.
Só usa a biblioteca padrão do Python: recebe as bases já carregadas e faz as "conexões" entre elas.

Cada função recebe (bases, argumentos) e devolve um dicionário enxuto, só com o que o modelo precisa.
"""
import unicodedata
from datetime import date


def _indice(linhas: list[dict], chave: str) -> dict:
    return {linha[chave]: linha for linha in linhas}


def _normalizar(texto: str) -> str:
    """'Clínica Geral' e 'clinica geral' viram a mesma coisa."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _dia_da_semana(data: str) -> str:
    """O modelo erra conta de calendário. A ferramenta já entrega o dia da semana pronto."""
    return _DIAS[date.fromisoformat(data).weekday()]


def _com_medico(item: dict, medicos: dict) -> dict:
    medico = medicos[item["medico_id"]]
    return {"medico": medico["nome"], "especialidade": medico["especialidade"], "unidade": medico["unidade"]}


def buscar_consultas(bases: dict, args: dict) -> dict:
    medicos = _indice(bases["medicos"], "medico_id")
    consultas = [
        {"consulta_id": c["consulta_id"], "data": c["data"], "dia_da_semana": _dia_da_semana(c["data"]), "hora": c["hora"],
         "status": c["status"], **_com_medico(c, medicos)}
        for c in bases["consultas"]
        if c["paciente_id"] == args["paciente_id"] and c["status"] in ("agendada", "remarcada")
    ]
    return {"paciente_id": args["paciente_id"], "consultas": sorted(consultas, key=lambda c: (c["data"], c["hora"]))}


def buscar_horarios(bases: dict, args: dict) -> dict:
    medicos = _indice(bases["medicos"], "medico_id")
    alvo = _normalizar(args["especialidade"])
    a_partir_de = args.get("a_partir_de") or date.today().isoformat()
    livres = [
        {"horario_id": h["horario_id"], "data": h["data"], "dia_da_semana": _dia_da_semana(h["data"]), "hora": h["hora"],
         **_com_medico(h, medicos)}
        for h in bases["horarios"]
        if h["livre"] is True
        and h["data"] >= a_partir_de
        and _normalizar(medicos[h["medico_id"]]["especialidade"]) == alvo
    ]
    livres.sort(key=lambda h: (h["data"], h["hora"]))
    return {"especialidade": args["especialidade"], "horarios_livres": livres[:6]}


def buscar_exames(bases: dict, args: dict) -> dict:
    medicos = _indice(bases["medicos"], "medico_id")
    exames = [
        {"pedido_id": e["pedido_id"], "exame": e["exame"], "situacao": e["situacao"],
         "pedido_em": e["data_pedido"], "pedido_por": medicos[e["medico_id"]]["nome"]}
        for e in bases["exames"]
        if e["paciente_id"] == args["paciente_id"]
    ]
    return {"paciente_id": args["paciente_id"], "exames": exames}


def remarcar_consulta(bases: dict, args: dict) -> dict:
    """Altera a agenda. Tem três travas no código, além da regra no prompt:
    confirmação explícita, consulta do próprio paciente e horário livre da mesma especialidade."""
    if args.get("confirmado_pelo_paciente") is not True:
        return {"ok": False, "motivo": "A remarcação precisa da confirmação explícita do paciente."}

    medicos = _indice(bases["medicos"], "medico_id")
    consulta = _indice(bases["consultas"], "consulta_id").get(args["consulta_id"])
    horario = _indice(bases["horarios"], "horario_id").get(args["horario_id"])

    if not consulta or consulta["paciente_id"] != args["paciente_id"]:
        return {"ok": False, "motivo": "Consulta não encontrada para este paciente."}
    if consulta["status"] not in ("agendada", "remarcada"):
        return {"ok": False, "motivo": f"A consulta está com status '{consulta['status']}'."}
    if not horario or horario["livre"] is not True:
        return {"ok": False, "motivo": "Esse horário não está mais livre."}
    if medicos[horario["medico_id"]]["especialidade"] != medicos[consulta["medico_id"]]["especialidade"]:
        return {"ok": False, "motivo": "O horário é de outra especialidade."}

    # Libera o horário antigo (se ele estiver na grade) e ocupa o novo
    for h in bases["horarios"]:
        if (h["medico_id"], h["data"], h["hora"]) == (consulta["medico_id"], consulta["data"], consulta["hora"]):
            h["livre"] = True
    horario["livre"] = False
    consulta.update(medico_id=horario["medico_id"], data=horario["data"], hora=horario["hora"], status="remarcada")

    return {"ok": True, "consulta": {"consulta_id": consulta["consulta_id"], "data": consulta["data"],
                                     "dia_da_semana": _dia_da_semana(consulta["data"]), "hora": consulta["hora"],
                                     **_com_medico(consulta, medicos)}}


# Nome da ferramenta (como está no Gateway) -> (função, altera as bases?)
FERRAMENTAS = {
    "buscar_consultas": (buscar_consultas, False),
    "buscar_horarios": (buscar_horarios, False),
    "buscar_exames": (buscar_exames, False),
    "remarcar_consulta": (remarcar_consulta, True),
}
