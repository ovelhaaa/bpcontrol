# BPControl M1H — interface do inspector, estado de rascunho e atividade

## Origem e decisão

O operador confirmou na placa BP1032 que **Aplicar** e **Desfazer**
funcionam na interface M1G (2026-11-22). A M1H é uma melhoria de
apresentação e inspeção: **não amplia a allowlist USB de escrita**.

A lição fundamental da captura ACPWorkbench M1E continua preservada:
digitar `80` → apagar `0` → digitar `1` gerou valores intermediários
`8` e `81` no ACPWorkbench. BPControl nunca transmite as alterações
intermediárias de texto; somente um clique ou Enter, seguido de confirmação.

## Implementado

A mesma entrada `tools/chorus_editor_gui.py` passa a mostrar o título M1H,
uma janela desktop Tkinter (sem servidor), com tema off-white, grafite
e laranja, sem dependências novas:

1. **Navegação por grupo e busca:** Todos, Music, Mic, Guitar, Rec,
   Other; contagem de instâncias filtradas e 59 itens no catálogo completo.
2. **Duas abas:** Parâmetros e Atividade da sessão. A aba de atividade
   mostra as solicitações e os resultados dos comandos `Consultar`,
   `Aplicar` e `Desfazer`, mais o cancelamento de rascunho.
3. **Origem dos valores explícita:** `Snapshot salvo` para os efeitos
   não lidos ao vivo; `USB / leitura atual` somente para os sete campos
   do Chorus após consulta manual bem-sucedida. Os valores do snapshot
   **não são tratados como valores vivos**.
4. **Confiança de mapeamento:** nome do campo, unidade, indicação
   de dado inferido/sem validação ou mapeado. Isso não constitui
   autorização de escrita.
5. **Valor confirmado no DSP separado do rascunho:** um indicador
   mostra o wet lido ao vivo; outro mostra, como prévia, alteração
   pendente e diferença, por exemplo `80 → 79 (-1)`.
6. **Aplicar só quando o rascunho é válido:** exatamente `±1`,
   inteiro `0..100`, e leitura física do Chorus disponível. Um
   rascunho como `8` partindo de `80` aparece como diferença
   inválida `-72`, sem habilitar Apply. Digitação, perda de
   foco e Backspace não fazem chamadas USB.
7. **Histórico temporário da sessão:** até 100 eventos resumidos,
   hora local, resultado do readback, identificação de consulta,
   Apply e Undo; botão para copiar; **sem gravação de arquivo**
   e sem exportação automática de dados.
8. **Validação mais forte das respostas do worker:** além do código
   de saída do processo, respostas `READ_OK` precisam conter
   exatamente sete valores inteiros e wet em 0..100. Respostas
   `APPLIED_VERIFIED` precisam comprovar ACK, alvo idêntico ao
   pedido, baseline idêntico ao esperado e os sete valores com
   apenas o wet alterado no ponto autorizado. Respostas
   inconsistentes **não são tratadas como sucesso**.

A lógica pura fica em `src/bpcontrol/editor_view_model.py` e é testada
sem abrir Tkinter nem USB.

## Como experimentar sem acessar hardware

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

Neste modo, a aplicação pode carregar o snapshot `artifacts/snapshots/bp1032-01.json`
ou o demonstrativo `data/demo_snapshot.json`; operações USB continuam
desabilitadas. Teste o filtro, a busca, a origem dos valores e
a aba de histórico.

## Primeiro ensaio físico da M1H (ainda pendente)

Depois de conferir a apresentação offline, com ACPWorkbench fechado,
BP1032 conectada e áudio baixo/mutado:

```powershell
py tools/chorus_editor_gui.py --enable-live-writes
```

A abertura da janela **não faz uma consulta nem inicia uma escrita**.

1. Escolher grupo Guitar, selecionar Chorus `0x8F`.
2. Clicar `Consultar Chorus (USB)`: o valor confirmado deve
   aparecer separado do valor do snapshot.
3. Apagar um dígito no campo, digitar um valor intermediário e
   confirmar que o botão Aplicar continua inativo para diferença
   superior a um ponto. Não há escrita enquanto digita.
4. Digitar um ponto acima/abaixo do valor confirmado,
   observar prévia verde com `±1`, clicar Aplicar e confirmar.
5. Verificar `APPLIED_VERIFIED` e o valor atualizado; depois
   usar Desfazer para voltar ao estado anterior.
6. Abrir aba `Atividade da sessão` e verificar os registros
   de leitura, Apply e Undo. O histórico está apenas em memória.
7. Opcionalmente copiar o histórico textual, omitir informações
   pessoais locais e compartilhar o resultado da M1H para revisão.

## Salvaguardas inalteradas

- Só o campo 6 (wet) de Guitar Chorus `0x8F` é gravável.
- Cada Apply autorizado altera **exatamente um ponto**.
- O backend verifica a identidade do firmware `0x30/0.3.0/2.24.0`,
  compara os sete campos atuais com a leitura manual salva e
  recusa conflitos antes de qualquer escrita.
- Cada escrita envia um `SET_REPORT` + `GET_REPORT` e readback
  completo de sete campos, num processo filho com timeout.
- Erro posterior ao envio provoca **uma tentativa** de restauração;
  se a restauração não for comprovada, a sessão de GUI bloqueia
  novas escritas e exige verificação manual após o encerramento
  do worker.
- Nunca enviar `0xFD` (salvar na flash), `0xFE` (atualizar firmware),
  resets, alterações em outros efeitos, MIDI ou fluxo contínuo.
- Uma aprovação da interface gráfica não é prova de resistência a
  desconexão elétrica ou atomicidade de restauração.

## Aceitação

A M1H pode ser considerada **implementada e aprovada nos testes offline**
quando o CI Windows/Linux passar. A experiência visual e o fluxo de
confirmação M1H **continuam dependentes da avaliação do operador na
placa real**. O sucesso físico da M1G não substitui essa checagem.

Arquivos relacionados:

- [`tools/chorus_editor_gui.py`](../tools/chorus_editor_gui.py)
- [`src/bpcontrol/editor_view_model.py`](../src/bpcontrol/editor_view_model.py)
- [`tests/test_editor_view_model.py`](../tests/test_editor_view_model.py)
- [`docs/M1G_GUI_EDITOR.md`](M1G_GUI_EDITOR.md)
- [`docs/ROADMAP.md`](ROADMAP.md)
