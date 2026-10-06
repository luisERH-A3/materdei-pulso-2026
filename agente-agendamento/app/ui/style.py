"""A aparência da interface: o CSS, os ícones e os pequenos blocos de HTML que as telas reaproveitam."""
import html
import re

import streamlit as st

# Ícones em SVG, desenhados na própria página: não dependem de fonte nem de internet. Traço na cor do texto.
_TRACOS = {
    "paciente": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "enviar": '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
    "preparo": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/>',
    "guardrail": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    "modelo": '<path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/>',
    "ferramenta": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "resposta": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "relogio": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "loop": '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
    "tokens": '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
    "rede": '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9z"/>',
    "alerta": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><path d="M12 9v4M12 17h.01"/>',
    "feito": '<path d="M20 6 9 17l-5-5"/>',
}


def icone(nome: str) -> str:
    return (f'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_TRACOS[nome]}</svg>')


def curto(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else texto[: limite - 3] + "..."


def duracao(ms: float | None) -> str:
    """420 ms ou 1,2 s: o que cabe numa etiqueta."""
    if ms is None:
        return ""
    return f"{round(ms)} ms" if ms < 1000 else f"{ms / 1000:.1f} s".replace(".", ",")


def com_quebras(texto: str) -> str:
    """No Markdown, uma quebra de linha simples some. Aqui ela vira quebra de verdade, para as listas do agente."""
    return re.sub(r"(?<!\n)\n(?!\n)", "  \n", texto)


def dica(texto: str) -> str:
    """O ícone amarelo com exclamação: a explicação aparece ao passar o mouse (ou ao focar com o teclado)."""
    return f'<span class="dica" tabindex="0">!<span class="balao">{html.escape(texto)}</span></span>'


def titulo(texto: str, explicacao: str) -> None:
    """Um título curto, com a explicação guardada na dica."""
    st.markdown(f'<div class="titulo">{html.escape(texto)}{dica(explicacao)}</div>', unsafe_allow_html=True)


def mostrar_json(dado, chave: str) -> None:
    """Todo JSON da tela vem recolhido, com um botão para abrir tudo de uma vez."""
    tudo = st.toggle("Expandir tudo", key=f"json-{chave}")
    st.json(dado, expanded=True if tudo else 1)


def etiquetas(itens: list[tuple[str, str, str]]) -> str:
    """Uma fileira de etiquetas: (ícone, texto, classe). É o resumo de uma resposta, no chat e no painel."""
    return '<div class="etiquetas">' + "".join(
        f'<span class="etiqueta {classe}">{icone(nome)}{html.escape(texto)}</span>' for nome, texto, classe in itens
    ) + "</div>"


# Cores com papel fixo em toda a tela: modelo, ferramenta, guardrail, preparo e rede.
ESTILO = """
<style>
  :root { --modelo: #0f6e84; --ferramenta: #d9662b; --guardrail: #2f9e6e; --preparo: #7b8794; --rede: #b9c2cc;
          --alerta: #c98a04; --erro: #c8372d; --linha: rgba(128, 128, 128, .28); --fundo: rgba(128, 128, 128, .07); }
  .ico { width: 1em; height: 1em; flex: none; vertical-align: -0.14em; }

  /* título de seção e dica (a exclamação amarela) */
  .titulo { font-weight: 600; font-size: 1rem; margin: 14px 0 6px; }
  .dica { display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px; margin-left: 6px;
          border-radius: 50%; background: #facc15; color: #422006; font-size: 11px; font-weight: 700; line-height: 1;
          cursor: help; position: relative; vertical-align: middle; flex: none; }
  @keyframes abrir { from { opacity: 0; margin-top: -4px; } to { opacity: 1; margin-top: 0; } }
  .dica .balao { display: none; position: fixed; transform: translate(-50%, 16px); z-index: 999999;  /* fixed: nenhum painel recorta */
                 width: 280px; max-width: 70vw; padding: 10px 12px; border-radius: 10px; background: #1f2937; color: #f9fafb;
                 font-size: .8rem; font-weight: 400; line-height: 1.45; text-align: left; white-space: normal;
                 text-transform: none; letter-spacing: normal; box-shadow: 0 8px 24px rgba(0, 0, 0, .25); }
  .dica:hover .balao, .dica:focus .balao { display: block; animation: abrir .15s ease both; }

  /* etiquetas: o resumo de uma resposta */
  .etiquetas { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 2px; }
  .etiqueta { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px; border-radius: 999px; font-size: .76rem;
              background: var(--fundo); border: 1px solid var(--linha); font-variant-numeric: tabular-nums; white-space: nowrap; }
  .etiqueta.ok { color: var(--guardrail); border-color: currentColor; }
  .etiqueta.alerta { color: var(--alerta); border-color: currentColor; }
  .etiqueta.erro { color: var(--erro); border-color: currentColor; }

  /* andamento: o que o agente está fazendo enquanto a resposta não chega */
  @property --seg { syntax: "<integer>"; initial-value: 0; inherits: false; }
  @keyframes contar { to { --seg: 600; } }
  @keyframes pulsar { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, currentColor 45%, transparent); }
                      60% { box-shadow: 0 0 0 7px transparent; } }
  @keyframes entrar { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: none; } }
  .andamento { display: flex; flex-direction: column; gap: 0; margin: 2px 0 6px; font-size: .88rem; }
  .andamento .passo { display: grid; grid-template-columns: 26px 1fr auto; align-items: center; gap: 8px; padding: 3px 0;
                      position: relative; opacity: .62; }
  .andamento .passo::before { content: ""; position: absolute; left: 12px; top: -8px; height: 10px; width: 2px; background: var(--linha); }
  .andamento .passo:first-child::before { display: none; }
  .andamento .bola { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; font-size: .85rem;
                     background: var(--fundo); border: 1px solid var(--linha); }
  .andamento .passo small { opacity: .7; font-variant-numeric: tabular-nums; }
  .andamento .passo .sub { display: block; font-size: .76rem; opacity: .75; overflow-wrap: anywhere; }
  .andamento .passo.agora { opacity: 1; font-weight: 600; animation: entrar .25s ease both; }
  .andamento .passo.agora .bola { color: var(--cor, var(--modelo)); border-color: currentColor; animation: pulsar 1.4s ease-out infinite; }
  .andamento .modelo { --cor: var(--modelo); } .andamento .ferramenta { --cor: var(--ferramenta); }
  .andamento .preparo, .andamento .enviar { --cor: var(--preparo); } .andamento .alerta { --cor: var(--alerta); }
  .andamento .resposta { --cor: var(--guardrail); }
  .cronometro { counter-reset: seg var(--seg); animation: contar 600s linear both; }
  .cronometro::after { content: counter(seg) " s"; }

  /* onde foi o tempo: uma barra, um pedaço por etapa */
  .tempos { margin: 8px 0 12px; }
  .tempos .barra { display: flex; height: 22px; border-radius: 7px; overflow: hidden; background: var(--fundo); }
  .tempos .barra span { min-width: 2px; transition: flex-grow .5s ease; }
  .tempos .legenda { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; font-size: .8rem; }
  .tempos .legenda span { display: inline-flex; align-items: center; gap: 6px; font-variant-numeric: tabular-nums; }
  .tempos .legenda i { width: 10px; height: 10px; border-radius: 3px; flex: none; }
  .tempos .legenda b { font-weight: 600; }
  .tempos .modelo, .fluxo .no.modelo .bola { background: var(--modelo); } .tempos .ferramenta { background: var(--ferramenta); }
  .tempos .guardrail { background: var(--guardrail); } .tempos .preparo { background: var(--preparo); }
  .tempos .rede { background: var(--rede); }
  .tempos .chamadas { display: flex; flex-direction: column; gap: 3px; margin-top: 10px; font-size: .78rem; }
  .tempos .chamada { display: grid; grid-template-columns: minmax(150px, 48%) 1fr 56px; gap: 8px; align-items: center; }
  .tempos .chamada div { height: 8px; border-radius: 4px; background: var(--fundo); overflow: hidden; }
  .tempos .chamada div span { display: block; height: 100%; border-radius: 4px; }
  .tempos .chamada em { font-style: normal; text-align: right; font-variant-numeric: tabular-nums; opacity: .8; }
  .tempos .chamada > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  /* fluxograma */
  .fluxo { display: flex; flex-direction: column; align-items: center; margin: 6px 0 14px; }
  .fluxo .no { width: min(100%, 560px); padding: 8px 12px 8px 10px; border-radius: 12px; border: 1px solid var(--linha);
               background: var(--fundo); font-size: .85rem; display: grid; grid-template-columns: 26px 1fr; column-gap: 9px; }
  .fluxo .no .bola { grid-row: span 2; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
                     background: var(--preparo); color: #fff; font-size: .82rem; align-self: start; }
  .fluxo .no b { font-weight: 600; }
  .fluxo .no small { grid-column: 2; display: block; opacity: .75; margin-top: 1px; overflow-wrap: anywhere; }
  .fluxo .ponta { border-radius: 999px; }
  .fluxo .ferramenta .bola { background: var(--ferramenta); }
  .fluxo .ferramenta small { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .76rem; }
  .fluxo .ok .bola { background: var(--guardrail); }
  .fluxo .alerta { background: color-mix(in srgb, var(--alerta) 10%, transparent); } .fluxo .alerta .bola { background: var(--alerta); }
  .fluxo .erro { background: color-mix(in srgb, var(--erro) 10%, transparent); } .fluxo .erro .bola { background: var(--erro); }
  .fluxo .liga { display: flex; flex-direction: column; align-items: center; font-size: .72rem; opacity: .6; padding: 1px 0; }
  .fluxo .liga::before { content: ""; width: 2px; height: 12px; background: currentColor; opacity: .5; }
  .fluxo .liga::after { content: "▾"; line-height: .7; }
  .fluxo .ramos { display: flex; flex-wrap: wrap; gap: 8px; width: min(100%, 560px); }
  .fluxo .ramos .no { flex: 1 1 210px; min-width: 0; }  /* lado a lado enquanto couber; depois, quebra a linha */
  .fluxo .tempo { float: right; margin-left: 8px; padding: 0 8px; border-radius: 999px; font-size: .72rem;
                  background: rgba(128, 128, 128, .16); font-variant-numeric: tabular-nums; }
  .fluxo .marca { display: inline-block; margin-left: 6px; padding: 0 7px; border-radius: 999px; font-size: .7rem;
                  border: 1px solid currentColor; opacity: .8; }

  /* memória */
  .cartoes { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 6px 0 12px; }
  .cartao { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--linha); font-size: .85rem; }
  .cartao.ligada { border-color: var(--guardrail); background: color-mix(in srgb, var(--guardrail) 8%, transparent); }
  .cartao.desligada { opacity: .75; }
  .cartao b { display: block; margin-bottom: 2px; }
  .cartao .estado { float: right; font-size: .72rem; font-weight: 700; }
  .cartao.ligada .estado { color: var(--guardrail); }
  .numeros { display: flex; gap: 18px; flex-wrap: wrap; margin: 0 0 10px; font-size: .82rem; opacity: .85; }
  .numeros b { font-size: 1.05rem; margin-right: 4px; }
  .linha { display: flex; gap: 8px; padding: 5px 0; font-size: .85rem; border-bottom: 1px solid rgba(128, 128, 128, .15); }
  .linha .quem { flex: none; width: 78px; font-size: .76rem; font-weight: 700; padding-top: 2px; opacity: .7; }
  .linha .quem.agente { color: var(--modelo); opacity: 1; }
  .linha .quem.ferramenta { color: var(--ferramenta); opacity: 1; }
  .linha code { font-size: .78rem; }
  .linha .fala { min-width: 0; overflow-wrap: anywhere; }

  .trecho { margin: 6px 0 10px; font-size: .88rem; }
  .trecho .barra { height: 4px; border-radius: 2px; background: var(--guardrail); margin: 3px 0; }
  .trecho small { opacity: .75; }

  /* a barra do topo: presa enquanto a página rola, com o título, o modo debug e o apagar */
  [data-testid="stLayoutWrapper"]:has(> .st-key-topo) { position: sticky; top: 3.75rem; z-index: 99; background: var(--papel, #fff);
                                                         padding: 8px 0 10px; border-bottom: 1px solid var(--linha); }
  .marca b { display: block; font-size: 1.45rem; font-weight: 700; line-height: 1.2; }
  .marca span { font-size: .8rem; opacity: .65; }

  /* histórico: cada conversa é um botão do tamanho da linha, com o título em cima e os dados embaixo */
  [class*="st-key-conversas"] { overflow-x: hidden; }
  [class*="st-key-conversas"] [data-testid="stVerticalBlock"] { gap: 4px; }
  [class*="st-key-conversas"] button, [class*="st-key-conversas"] button * { min-width: 0; max-width: 100%; box-sizing: border-box; }
  [class*="st-key-conversas"] button { display: block; width: 100%; text-align: left; padding: 7px 10px; border-radius: 10px;
                                       border: 1px solid transparent; background: transparent; color: inherit; }
  [class*="st-key-conversas"] button:hover { background: var(--fundo); border-color: var(--linha); color: inherit; }
  [class*="st-key-conversas"] button[kind="primary"] { background: var(--fundo); border-color: var(--modelo); }
  [class*="st-key-conversas"] button div, [class*="st-key-conversas"] button p { display: block; width: 100%; text-align: left; }
  [class*="st-key-conversas"] button p { font-size: .74rem; opacity: .8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  [class*="st-key-conversas"] button p strong { display: block; font-size: .86rem; font-weight: 600; opacity: 1;
                                                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  [data-testid="stExpander"] details { border-radius: 12px; }

  @media (max-width: 700px) { .cartoes { grid-template-columns: 1fr; } .tempos .chamada { grid-template-columns: 96px 1fr 50px; } }
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
    .cronometro { animation: contar 600s linear both !important; }  /* o contador de segundos é informação, não enfeite */
  }
</style>
"""
