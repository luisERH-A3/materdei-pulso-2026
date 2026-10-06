# Pulso.AI · Trilha Tech · Módulos 2 e 3

Material das aulas de outubro de 2026 para a Rede Mater Dei: os slides, o notebook do Módulo 2 e o projeto Python usado na demonstração ao vivo.

Na demo, um agente atende pacientes de uma rede de saúde **fictícia**: mostra as consultas, oferece horários, remarca **só depois do "sim"** e tira dúvidas de preparo de exames lendo os documentos da Rede (RAG). Tudo é serverless, em `us-east-1`.

**Aluno da turma?** Siga o [guia de início](docs/guia-de-inicio.md): do login no console da AWS ao agente funcionando, passo a passo, sem instalar nada no seu computador.

## Estrutura

```
pulso-trilha-tech/
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

Todos os comandos abaixo são para rodar **na raiz do repositório**. Há dois lugares para rodar, e o `demo.sh` reconhece cada um:

| Onde | Para quem | O que tem | Custo |
|---|---|---|---|
| **SageMaker Studio** | Os alunos da turma. Veja o [guia de início](docs/guia-de-inicio.md) | Arquivos, editor, Jupyter, terminal e a tela web do chat, tudo no navegador, sem instalar nada | Cerca de US$ 0,05 por hora de ambiente ligado |
| **Na sua máquina** | Quem já desenvolve | Tudo, com o seu editor | Só o uso da AWS |

No Studio não há nada para instalar nem login para fazer: pule o `aws login` e defina o `PROJETO`.

**Na sua máquina, você precisa de:** uma conta AWS, [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) e [uv](https://docs.astral.sh/uv/). Use Linux, macOS ou WSL.

```bash
aws login                            # 1. entre na sua conta AWS
bash agente-agendamento/demo.sh      # 2. implanta tudo, prepara os dados e abre o chat
```

São cerca de 5 minutos na primeira vez. O script cria o ambiente Python, testa o modelo, implanta a stack, carrega os dados e abre o chat no navegador.

| Comando | O que faz |
|---|---|
| `bash agente-agendamento/demo.sh` | Implanta tudo: o agente roda no AgentCore Runtime, e as ferramentas da agenda são uma Lambda publicada pelo AgentCore Gateway. Precisa de permissão para criar papéis IAM |
| `bash agente-agendamento/demo.sh abrir` | Abre o chat de novo, com a demo já implantada |
| `bash agente-agendamento/demo.sh remover` | Apaga da AWS tudo o que a demo criou |

**Opções**, escritas antes do comando:

- `MODELO_CONVERSA=moonshotai.kimi-k2.5 bash agente-agendamento/demo.sh` usa outro modelo. O padrão é o GPT-5.6 Luna (`us.openai.gpt-5.6-luna`). Se a conta não tiver acesso, o script avisa antes de implantar.
- `PROJETO=aluno01 bash agente-agendamento/demo.sh` troca o prefixo dos recursos, para várias pessoas dividirem a mesma conta.

**Alunos: o `PROJETO` é obrigatório e tem regras.** Na conta da turma, o seu acesso só permite criar recursos cujo nome começa com `aluno`. Se rodar sem `PROJETO`, o padrão (`pulso`) é negado e você recebe `AccessDenied`.

- Use um prefixo que comece com `aluno` e seja só seu, por exemplo `aluno01`, `aluno02`. Ele deve ter de 3 a 12 caracteres, em minúsculas e números, e começar com letra.
- Dois alunos com o mesmo prefixo sobrescrevem a stack um do outro. Combine com o professor qual é o seu.
- O orçamento da conta é de **US$ 80 por mês, somado, para a turma inteira**. Se passar, o acesso de todos é bloqueado. Teste o mínimo necessário para demonstrar.
- Use o mesmo prefixo em todos os comandos, inclusive em `abrir` e `remover`, senão o script não acha a sua stack. Depois da primeira implantação, o script guarda o prefixo em `agente-agendamento/.projeto`:
  ```bash
  export PROJETO=aluno01                  # vale para o terminal inteiro
  bash agente-agendamento/demo.sh
  bash agente-agendamento/demo.sh abrir
  bash agente-agendamento/demo.sh remover # ao terminar, para não deixar recursos na conta
  ```
- Rode sempre em `us-east-1`. Seu acesso para implantar só vale nessa região.
- A implantação cria papéis IAM, mas só os de nome `aluno*-agenda-lambda`, `aluno*-gateway` e `aluno*-agente-runtime`.

**Para experimentar no chat** (a tela já traz estes botões):

- "Quais são as minhas próximas consultas?"
- "Preciso remarcar a consulta de cardiologia." Depois escolha uma opção e confirme com "sim".
- "O exame de glicemia precisa de jejum?"
- "Quero trocar o meu convênio."
- A mensagem da Dona Helena, da história dos slides: três pedidos em um texto só.

**Se algo der errado**, a própria tela diz o que fazer. Os dois casos mais comuns:

- **O login da AWS expirou** (ele dura poucas horas): rode `aws login` e envie a mensagem de novo.
- **A primeira mensagem de uma conversa leva de 7 a 12 segundos** e as seguintes de 5 a 6. Ao abrir uma conversa, a interface já avisa o Runtime para ligar o ambiente daquela sessão (o aquecimento, que não chama o modelo). Se a mensagem chegar antes de ele terminar, ela espera esse preparo.

## O que a interface mostra

Os prints de cada tela estão na seção 4 de `docs/arquitetura.html`.

A tela abre só com o chat, como o paciente veria. Enquanto o agente trabalha, o chat mostra o passo em que ele está (preparando, entendendo o pedido, consultando a agenda, escrevendo), com um contador de segundos.

Cada conversa fica salva em `agente-agendamento/logs/conversas/`, já no envio da mensagem, e aparece na barra lateral, em **Histórico**, com as de todos os pacientes. Um clique reabre a conversa com o rastro de cada resposta, para analisar no modo debug, e troca o paciente da tela junto. Abrir outra conversa não perde a atual. Para apagar a conversa aberta, use o botão **Apagar conversa**, no topo, que pede uma confirmação. Dentro de 7 dias, o prazo do AgentCore Memory, ela também continua de onde parou.

O **Modo debug**, na barra do topo, abre ao lado o painel "Por dentro do agente". A barra fica presa enquanto a página rola, então dá para ligar e desligar a qualquer momento, inclusive numa conversa do histórico. As explicações ficam nos ícones amarelos com exclamação: passe o mouse para ler.

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
- **Mudar os dados, e antes de cada aula:** rode `agente-agendamento/.venv/bin/python agente-agendamento/data/prepare.py`. Ele envia o Excel de novo, desfaz as remarcações feitas no chat e avança as datas da agenda em semanas inteiras quando as do Excel já passaram.
- **Notebook:** no Studio, escolha o kernel **Pulso (.venv)**, que o `demo.sh` registra. Na sua máquina, use o kernel do `.venv` do projeto. O `requirements.txt` já inclui o que ele precisa.
- **LGPD:** os dados são fictícios e ficam nos EUA. A memória expira em 7 dias.
- **Custo:** você paga só pelo uso. Para remover tudo: `bash agente-agendamento/demo.sh remover`.
- **Escopo:** é material de aula, com dados fictícios, e o desenho não foi preparado para uso real. Ficaram de fora, de propósito: AgentCore Policy, memória de longo prazo e login.
