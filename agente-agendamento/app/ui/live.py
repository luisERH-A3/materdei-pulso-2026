"""O andamento de uma resposta: enquanto o agente trabalha, o chat mostra o passo em que ele está.

O agente avisa cada passo por um evento do stream (veja app/agent/main.py). Aqui cada aviso vira uma linha, com
um contador de segundos no passo atual. No fim, os passos e os tempos ficam guardados com a mensagem.
"""
import html
import time

from style import duracao, icone

# O que o paciente lê enquanto cada ferramenta roda
FRASES = {
    "consultar_orientacoes": "Consultando as orientações da Rede",
    "buscar_consultas": "Buscando as suas consultas",
    "buscar_horarios": "Procurando horários livres",
    "buscar_exames": "Buscando os seus exames",
    "remarcar_consulta": "Remarcando a consulta",
}
_ICONES = {"enviar": "enviar", "preparo": "preparo", "modelo": "modelo", "ferramenta": "ferramenta", "resposta": "resposta", "alerta": "alerta"}


class Andamento:
    """A lista de passos de uma resposta, desenhada numa área da tela que é reescrita a cada evento."""

    def __init__(self, area, tecnico: bool):
        self.area = area
        self.tecnico = tecnico  # no modo debug, cada passo mostra também o nome técnico
        self.inicio = time.perf_counter()
        self.passos = []
        self.passo("enviar", "Enviando a mensagem ao agente", "a rede e o AgentCore Runtime")

    @property
    def atual(self) -> str:
        return self.passos[-1]["tipo"]

    def passo(self, tipo: str, texto: str, detalhe: str = "") -> None:
        """Fecha o passo anterior, com o tempo que levou, e abre o próximo."""
        agora = time.perf_counter()
        if self.passos:
            self.passos[-1]["ms"] = round((agora - self.passos[-1]["desde"]) * 1000)
        self.passos.append({"tipo": tipo, "texto": texto, "detalhe": detalhe, "desde": agora, "ms": None})
        self.desenhar()

    def juntar(self, texto: str, detalhe: str) -> None:
        """Mais uma ferramenta pedida na mesma chamada: entra no passo que já está aberto."""
        passo = self.passos[-1]
        if texto not in passo["texto"]:
            passo["texto"] += f" e {texto[0].lower()}{texto[1:]}"
        passo["detalhe"] += f", {detalhe}"
        self.desenhar()

    def encerrar(self) -> tuple[list[dict], int]:
        """Limpa a área e devolve os passos, com o tempo de cada um, e a espera total em milissegundos."""
        agora = time.perf_counter()
        self.passos[-1]["ms"] = round((agora - self.passos[-1]["desde"]) * 1000)
        self.area.empty()
        passos = [{chave: passo[chave] for chave in ("tipo", "texto", "detalhe", "ms")} for passo in self.passos]
        return passos, round((agora - self.inicio) * 1000)

    def desenhar(self) -> None:
        agora = time.perf_counter()
        linhas = []
        for passo in self.passos:
            feito = passo["ms"] is not None
            detalhe = f'<span class="sub">{html.escape(passo["detalhe"])}</span>' if self.tecnico and passo["detalhe"] else ""
            if feito:
                tempo = f"<small>{duracao(passo['ms'])}</small>"
            else:  # o contador anda sozinho, no navegador: o atraso negativo faz ele começar do tempo já decorrido
                tempo = f'<small class="cronometro" style="animation-delay:-{agora - passo["desde"]:.1f}s"></small>'
            linhas.append(
                f'<div class="passo {passo["tipo"]}{"" if feito else " agora"}">'
                f'<span class="bola">{icone("feito" if feito else _ICONES[passo["tipo"]])}</span>'
                f'<span>{html.escape(passo["texto"])}{detalhe}</span>{tempo}</div>'
            )
        self.area.markdown(f'<div class="andamento" role="status">{"".join(linhas)}</div>', unsafe_allow_html=True)
