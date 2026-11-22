# BPControl M1G — primeiro editor visual de parâmetros (Windows)

## Situação

A M1F foi aprovada pelo operador na placa física em 2026-11-22:
`PASS_RESTORED`, Chorus wet `80→79→80`, ACKs corretos e os sete
campos restaurados por readback. Esse teste validou **um único
parâmetro** e o caminho feliz de comunicação. Não libera escrita dos
outros 844 campos, alteração contínua ou flash save.

A M1G introduz um **protótipo gráfico Windows, usando tkinter (biblioteca
padrão do Python)**. Essa primeira GUI não substitui nem altera o
explorador HTML offline já existente. Ela poderá compartilhar o
backend de segurança com uma futura interface web; nesta versão,
escolhemos uma janela local para não expor comandos USB por HTTP.

**Esta implementação M1G é nova: testes de regressão offline não
equivalem a uma aprovação física da nova GUI.**

## Interface

- Lista navegável de **59 instâncias** do snapshot JSON, com busca.
- Tabela dos campos assinados, unidades e classificação de evidência.
- Para 58 instâncias, **sempre somente leitura**.
- Para Guitar Chorus `0x8F`, só o `wet` (campo 6) é editável;
  os seis demais parâmetros aparecem na tabela, mas não podem
  ser alterados.
- Botão **Consultar Chorus (USB)**: opt-in manual, sem polling.
- Campo numérico com rascunho local (não transmite cada caractere).
- Botões **Aplicar**, **Desfazer último Apply**, **Cancelar rascunho**.
- Enter inicia o mesmo fluxo que Aplicar; perder foco ou
  digitar `8` enquanto se edita `80` **não envia qualquer comando**.

O campo deve conter um inteiro decimal completo de 0 a 100, mas
**cada Apply M1G só aceita uma diferença de exatamente 1 ponto**.
Isso é intencional: a expansão para saltos maiores depende de
novos testes e mecanismos de recuperação.

## Como abrir sem tocar na placa

Abra PowerShell em `C:\progs\bpcontrol`:

```powershell
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

Por padrão:
- não abre USB/HID;
- não lê a BP1032 nem transmite comandos;
- carrega `artifacts/snapshots/bp1032-01.json` quando existe;
- caso contrário, exibe o snapshot demo (identificado);
- não habilita Apply nem Desfazer.

Também é possível indicar explicitamente uma captura:

```powershell
py tools/chorus_editor_gui.py --snapshot artifacts/snapshots/bp1032-01.json
```

O snapshot passa por auditoria estrutural antes de ser exibido.
Nomes de campos desconhecidos continuam sem escala aprovada.

## Habilitar o primeiro teste físico de edição pela GUI

**Somente depois de verificar o modo offline** e com
ACPWorkbench fechado, áudio silenciado ou baixo e nenhum outro
programa controlando o HID da BP1032:

```powershell
py tools/chorus_editor_gui.py --enable-live-writes
```

Esse argumento **não envia comandos ao abrir a janela**.
É preciso fazer, em ordem:

1. Selecionar Guitar Chorus (instância `0x8F`).
2. Clicar **Consultar Chorus (USB)**. A leitura executa num
   processo auxiliar, verifica o firmware e retorna o
   estado completo de sete parâmetros.
3. Digitar novo wet (por exemplo, **79** quando a consulta mostrou
   **80**). Pode-se editar livremente o rascunho; nenhum
   comando USB acontece nessa fase.
4. Clicar **Aplicar** ou usar Enter.
5. Conferir na caixa de confirmação o valor inicial e o
   pretendido, e aceitar explicitamente a escrita temporária.
6. O worker verifica novamente o firmware exato, lê **duas vezes**
   os sete campos, compara com a leitura manual anterior e
   **recusa** o comando se qualquer valor tiver mudado.
7. Só então emite **uma escrita** Chorus `0x8F` campo `6`,
   seguida de ACK e readback dos sete campos. O valor novo
   permanece ativo, mas não salvo em flash.
8. **Desfazer último Apply** requer outra confirmação e
   realiza **uma nova** escrita de um ponto de volta,
   com as mesmas validações e readback. Não é uma restauração
   automática após um Apply bem-sucedido.

O fluxo é assim porque M1F restaurava sempre, enquanto M1G
precisa permitir ouvir um estado temporariamente aplicado.
Uma escrita com sucesso é **volátil, não persistente**.

## Tratamento de erros e segurança

- Só são aceitos `0x00` (consulta firmware) e `0x8F`
  (leitura ou escrita estritamente do campo 6); os demais efeitos
  não têm API de escrita na M1G.
- Sem `0xFD` (salvamento persistente), `0xFE` (firmware),
  comandos de reset, polling, retries, MIDI ou presets.
- Se o estado lido na hora da operação divergir da
  leitura manual anterior: `REFUSED_NO_WRITE`, nenhum
  comando de alteração é enviado e é necessária outra consulta.
- Se houver erro depois de tentar alterar: a sessão tenta
  **uma** restauração do valor inicial e confere os sete campos.
- `ERROR_BUT_RESTORED` significa que a leitura final
  encontrou todos os sete campos iniciais, mas a operação
  não passou como Apply.
- `STATE_UNCERTAIN` significa que o valor pode ter
  sido alterado sem comprovação de restauração. A GUI bloqueia
  novas escritas até encerrar a sessão. Só depois do término
  do worker pode-se abrir o ACPWorkbench para verificar
  e restaurar manualmente o Chorus.
- Cada ação USB roda em processo filho com **timeout de 15 s**.
  Timeout não é rollback atômico: se ocorrer depois de uma
  escrita, pode deixar a placa com o valor alterado.
- Não se permite fechar a janela enquanto uma operação
  USB estiver em andamento.

O comando `tools/chorus_editor_worker.py` existe apenas para
ser chamado por essa GUI (o watchdog reside no processo pai).
Não executá-lo diretamente como interface de usuário.

## Evidências necessárias para homologar M1G física

1. Abrir em modo offline e conferir navegação e leitura das
   59 instâncias sem abrir USB.
2. Abrir com `--enable-live-writes`, consultar Chorus:
   deve mostrar o valor real atual sem escrita.
3. Digitar `8`, `81`, apagar/reverter para `80`:
   nenhum ACK/escrita deve ocorrer durante a digitação.
4. Confirmar uma alteração **de um ponto** (ex. 80→79),
   observar `APPLIED_VERIFIED`.
5. Usar Desfazer (79→80) e obter novo `APPLIED_VERIFIED`.
6. Confirmar que os seis outros campos permaneceram iguais.
7. Verificar mensagens e travas de erros sem forçar
   desconexões ou provocar falhas de propósito na placa.

**Aprovado na M1F:** transporte, ACK e restauração do wet do
Chorus. **Ainda pendente na M1G:** interação da GUI real,
comandos originados pelos botões e o fluxo de Desfazer.

Arquivos:
- [`tools/chorus_editor_gui.py`](../tools/chorus_editor_gui.py)
- [`tools/chorus_editor_worker.py`](../tools/chorus_editor_worker.py)
- [`src/bpcontrol/chorus_editor.py`](../src/bpcontrol/chorus_editor.py)
- [`tests/test_chorus_editor.py`](../tests/test_chorus_editor.py)
- [`M1F_FIRST_LIVE_WRITE.md`](M1F_FIRST_LIVE_WRITE.md)


## Feedback do operador (2026-11-22)

O proprietário informou **“funcionou”** após executar a M1G.
Registramos, portanto, que o protótipo gráfico funcionou no ambiente
Windows com BP1032 conectado. Não foi anexado, nesta atualização,
um log discriminando os resultados de **Consultar**, **Aplicar** e
**Desfazer**, nem uma nova captura USBPcap. Evitar afirmar
verificação independente de cada botão até receber essa evidência.

O ensaio anterior **M1F** continua sendo a comprovação física
detalhada disponível para a operação `wet 80→79→80`,
com ACKs e readbacks. A próxima iteração deve melhorar
usabilidade e instrumentação de status, preservando o escopo
restrito de escrita e as salvaguardas de restauração.

## Confirmação adicional — homologação funcional M1G (2026-11-22)

Após a primeira confirmação genérica, o proprietário respondeu
explicitamente **“sim, ambas operações funcionam”**, referindo-se
à execução de **Aplicar** e **Desfazer** na interface M1G com BP1032.

**Resultado:** os dois fluxos de operação gráfica foram **aceitos pelo
operador na placa física**. A M1G pode ser considerada funcionalmente
homologada nesse escopo: Chorus wet (campo 6), mudança unitária
volátil, confirmação explícita e Undo. A instrumentação de readback
está no código e teve testes offline; não recebemos log independente
contendo as duas respostas JSON da GUI nem USBPcap dessa rodada.

**Escopo da próxima M1H:** melhorias de UX e inspeção dos 59 efeitos,
sem ampliação automática da lista de parâmetros graváveis,
sem streams de escritas e sem persistência na flash.
