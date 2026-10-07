# Pulso.AI · Trilha Tech · Módulos 2 e 3

Material das aulas de outubro de 2026 para a Rede Mater Dei: os slides, o notebook do Módulo 2 e o projeto Python usado na demonstração ao vivo.

Na demo, um agente atende pacientes de uma rede de saúde **fictícia**: mostra as consultas, oferece horários, remarca **só depois do "sim"** e tira dúvidas de preparo de exames lendo os documentos da Rede (RAG). Tudo é serverless, em `us-east-1`.

**Comece pelo [guia de início](docs/guia-de-inicio.md):** do login no console da AWS ao agente funcionando, passo a passo, sem instalar nada.

## Estrutura

```
materdei-pulso-2026/
├── README.md                              este arquivo
├── docs/
│   ├── guia-de-inicio.md                  COMECE AQUI: do zero ao agente rodando, passo a passo
│   ├── arquitetura.html                   como a demo funciona: serviços, dados, uma conversa, a interface e observabilidade
│   ├── img/                               prints da interface, usados no guia e na arquitetura
│   ├── modulo2/
│   │   ├── modulo2-arquitetura-de-modelos.pdf      slides · 73 páginas
│   │   └── modulo2_arquitetura_de_modelos.ipynb    notebook de fim de módulo
│   └── modulo3/
│       └── modulo3-agentic-ai-deep-dive.pdf        slides · 63 páginas
└── agente-agendamento/                    o projeto da demonstração
    ├── demo.sh                            implantar, abrir e remover, em um comando
    ├── requirements.txt
    ├── app/
    │   ├── agent/                         O AGENTE: um só, sem supervisor nem subagentes
    │   │   ├── main.py                    entrada: recebe a mensagem (AgentCore Runtime)
    │   │   ├── agent.py                   junta as peças e roda o loop: pensar, agir, observar, repetir
    │   │   ├── model.py                   cérebro: o modelo no Bedrock, com o guardrail na mesma chamada
    │   │   ├── prompt.py                  instruções: o system prompt, do Bedrock Prompt Management
    │   │   ├── memory.py                  memória de curto prazo: AgentCore Memory
    │   │   ├── rag.py                     conhecimento: embeddings e busca no S3 Vectors
    │   │   ├── tools/                     mãos: as 5 ferramentas que o modelo pode pedir
    │   │   │   ├── guidelines.py          consultar_orientacoes: busca nos documentos (RAG)
    │   │   │   └── gateway.py             as 4 da agenda, vindas do AgentCore Gateway
    │   │   └── utils/                     config.py, logs.py (registro) e trace.py (o que a tela mostra)
    │   ├── schedule/                      o que as ferramentas da agenda fazem
    │   │   ├── rules.py                   consultas, horários, exames e remarcação, com as travas
    │   │   └── handler.py                 entrada da Lambda
    │   └── ui/                            chat em Streamlit, com o modo debug
    ├── data/                              bases fictícias
    │   ├── bases.xlsx                     pacientes, médicos, consultas, horários e exames
    │   ├── conhecimento.xlsx              os 15 documentos do RAG
    │   ├── sheets.py                      lê o Excel e confere as ligações entre as tabelas
    │   └── prepare.py                     Excel → S3 e S3 Vectors
    └── infra/                             CloudFormation
        └── completa/                      Runtime, Gateway, Lambda e papéis IAM
```

## Como rodar a demo

A demo roda no **SageMaker Studio**, o ambiente da turma na AWS: arquivos, editor, Jupyter, terminal e a tela do chat, tudo no navegador. O [guia de início](docs/guia-de-inicio.md) mostra como abrir o seu.

No terminal do JupyterLab, **na raiz do repositório**:

```bash
export PROJETO=alunomsouza           # o SEU prefixo, só na primeira vez
bash agente-agendamento/demo.sh      # implanta tudo, prepara os dados e sobe o chat
```

São cerca de 8 minutos na primeira vez. No fim, o terminal mostra o endereço do chat, que termina em `/proxy/8501/`: abra em outra aba.

| Comando | O que faz |
|---|---|
| `bash agente-agendamento/demo.sh` | Implanta ou atualiza a sua stack, prepara os dados e sobe o chat |
| `bash agente-agendamento/demo.sh abrir` | Sobe o chat de novo, com a demo já implantada |
| `bash agente-agendamento/demo.sh remover` | Apaga da AWS tudo o que a sua stack criou |

**O prefixo (`PROJETO`)** separa o que é seu do que é dos colegas:

- Começa com `aluno`, tem só letras minúsculas e números, no máximo 12 caracteres. Fora disso, a AWS responde `AccessDenied`.
- Não pode repetir o de um colega: quem repete sobrescreve a stack do outro.
- O script guarda o prefixo depois da primeira implantação, em `agente-agendamento/.projeto`.

**O orçamento é de US$ 80 por mês, somado, para a turma inteira.** Se passar, o acesso de todos é bloqueado. Teste o mínimo necessário para demonstrar, desligue o seu espaço ao terminar e remova a stack quando o projeto acabar.

**Outro modelo:** `MODELO_CONVERSA=moonshotai.kimi-k2.5 bash agente-agendamento/demo.sh`. O padrão é o GPT-5.6 Luna (`us.openai.gpt-5.6-luna`). Serve qualquer modelo do Bedrock que aceite ferramentas, e o script testa o acesso antes de implantar.

**Deu erro?** Veja a [seção 10 do guia](docs/guia-de-inicio.md#10-deu-erro).

## O que a interface mostra

Os prints de cada tela estão na seção 4 de `docs/arquitetura.html`.

A tela abre só com o chat, como o paciente veria, com botões para os pedidos de exemplo. Enquanto o agente trabalha, o chat mostra o passo em que ele está.

Cada conversa fica salva e aparece na barra lateral, em **Histórico**. Um clique reabre a conversa com o rastro de cada resposta, sem chamar o modelo de novo.

O **Modo debug**, na barra do topo, abre ao lado o painel "Por dentro do agente". As explicações ficam nos ícones amarelos com exclamação: passe o mouse para ler.

| Aba do modo debug | O que tem |
|---|---|
| Resposta | Onde foi o tempo: uma barra que reparte a espera entre preparo, modelo, guardrail, ferramentas e rede, e o tempo de cada chamada ao modelo. O caminho da resposta em um fluxograma. Abaixo, o passo a passo: o raciocínio do modelo, cada ferramenta com argumentos e resultado, os trechos do RAG com a similaridade e os tokens |
| Prompt | O que o modelo recebeu: o system prompt, o histórico, a mensagem do paciente e as ferramentas |
| Memória | A memória de curto prazo (ligada) e a de longo prazo (desligada), e o que o AgentCore Memory guardou |
| Dados | A agenda do paciente no S3, que muda ao remarcar, e os 15 textos do RAG |
| Vetores | Os vetores do S3 Vectors num mapa 2D interativo (PCA). Digite uma pergunta para ver onde ela cai no mapa |
| Na AWS | Links para ver cada recurso no console e o id da sessão para achar a conversa no AgentCore Observability |

Para ver o guardrail agir, abra "Testar o guardrail" na barra lateral: conselho clínico e ataque de prompt são bloqueados na entrada, sem chamar o modelo, e o CPF é mascarado na resposta.

## Onde está cada tema da aula

| Tema | Arquivo |
|---|---|
| Bedrock e Converse API | `agente-agendamento/app/agent/model.py` |
| Escolha de modelo e região | `agente-agendamento/app/agent/utils/config.py` |
| Prompt como código | `agente-agendamento/app/agent/prompt.py`, `infra/completa/template.yaml` |
| RAG: embeddings e busca | `agente-agendamento/app/agent/rag.py` |
| Ferramentas | `agente-agendamento/app/agent/tools/` |
| Humano no loop (as travas da remarcação) | `agente-agendamento/app/schedule/rules.py` |
| Agente e loop | `agente-agendamento/app/agent/agent.py` |
| Memória | `agente-agendamento/app/agent/memory.py` |
| Guardrails | `agente-agendamento/app/agent/model.py`, `infra/completa/template.yaml` |
| Thinking (nível de raciocínio) | `agente-agendamento/app/agent/model.py` |
| Interface e modo debug | `agente-agendamento/app/ui/` |
| Observabilidade (sessão, trace e span) | `agente-agendamento/app/agent/agent.py`, `docs/arquitetura.html` (seção 5) |
| Os dados | `agente-agendamento/data/` |
| Notebook do Módulo 2 | `docs/modulo2/modulo2_arquitetura_de_modelos.ipynb` |

## Bom saber

- **Mudar o prompt:** edite no console do Bedrock Prompt Management e crie uma versão. O agente usa a última versão publicada e a atualiza em até um minuto, sem reiniciar. Para fixar uma, defina `PROMPT_VERSAO` no `.env`.
- **Está lento ou deu erro?** No modo debug, a aba Resposta mostra onde foi o tempo de cada resposta. O mesmo registro fica no CloudWatch Logs do Runtime: o tempo de cada etapa, o de cada chamada ao modelo (`chamadas_ms`) e os erros, com o detalhe.
- **Trocar o modelo:** defina `MODELO_CONVERSA` no `.env`. Serve qualquer modelo do Bedrock que aceite ferramentas.
- **Mudar os dados ou desfazer as remarcações:** rode `agente-agendamento/.venv/bin/python agente-agendamento/data/prepare.py`. Ele envia o Excel de novo e avança as datas da agenda quando as do Excel já passaram.
- **Notebook:** escolha o kernel **Pulso (.venv)**, que o `demo.sh` registra.
- **LGPD:** os dados são fictícios e ficam nos EUA. A memória expira em 7 dias.
- **Custo:** a stack só cobra pelo uso, principalmente as chamadas ao modelo. O espaço do Studio cobra por hora ligado.
- **Escopo:** é material de aula, com dados fictícios, e o desenho não foi preparado para uso real. Ficaram de fora, de propósito: AgentCore Policy, memória de longo prazo e login.
