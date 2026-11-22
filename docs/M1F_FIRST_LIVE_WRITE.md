# BPControl M1F — primeiro controle de escrita USB: Chorus wet ±1 e restauração

## Situação e evidências

A etapa M1E foi validada em captura USBPcap real realizada pelo
operador em 2026-11-22. O tráfego mostrou:

- Chorus `0x8F`, campo 6 (wet): seis escritas, todas seguidas por
  ACK **`0x8F` + 255 bytes zero** no relatório USB de 256 bytes;
- Readbacks de cada alteração (`8, 81, 81, 8, 80, 80`) e confirmação
  de estado final do Chorus em `wet=80`;
- Auto Wah `0x90`, campo 0 (enable): mudança `0→1→0`, ACKs,
  e readback final em `0`, igual ao valor inicial;
- Os valores intermediários 8/81 são consistentes com a digitação
  incremental no campo numérico do ACPWorkbench, conforme explicou
  o operador; **não são evidência de falha no protocolo USB**.

Os testes offline do código M1F não substituem o primeiro ensaio real
do próprio BPControl. O M1F é intencionalmente limitado a **um único
campo e uma alteração temporária não persistente**.

## Escopo do M1F

`tools/probe_chorus_windows.py` usa
`src/bpcontrol/usb_chorus_probe.py`, que herda a sessão de leitura
Windows já validada mas implementa **somente** o quadro de escrita:

```text
A5 5A 8F 03 06 LL HH 16
```

- `0x8F` = Guitar Chorus; `0x06` = wet, em inteiro 0..100;
- `LL HH` = valor de destino de 16 bits, little-endian;
- ACK **estrito**: buffer Windows HID de 257 B = ID `00`,
  `8F` e 255 zeros; qualquer formato diferente é erro;
- Uma alteração de um ponto em direção a zero, exceto se
  valor inicial for zero (então altera para 1);
- **Uma** tentativa de alteração, **uma** tentativa de restauração,
  sem retransmitir comando que falhar;
- Nunca emite `0xFD` (save), `0xFE` (firmware), `0x01` (sistema),
  reset ou parâmetros de outros efeitos.

## Requisitos e comandos

Primeiro rodar testes offline:

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
```

**Atenção:** este é o primeiro programa BPControl com autorização
explícita para mudar temporariamente o DSP. Só execute
o próximo comando depois de confirmar que:

- BP1032 conectada, áudio mutado/baixo e ACPWorkbench **fechado**;
- Nenhum outro controlador HID usando a BP1032 simultaneamente;
- Aceita testar temporariamente `Chorus wet`, sem salvar na flash;
- O valor esperado `80` corresponde à leitura anterior; **não é
  assumido como valor atual**. O programa consulta o valor atual
  e recusa a operação se for diferente.

O operador pode optar por executar:

```powershell
py tools/probe_chorus_windows.py --live-chorus-probe --expect-wet 80 --authorize-one-temporary-write
```

Não há acesso ao hardware se uma das três opções faltar.
A execução exige Windows, interface HID MI_04 e firmware
`0x30 / 0.3.0 / DSP effects 2.24.0`. Um processo auxiliar
isolado executa a sequência com watchdog de **15 segundos**.

## Sequência de segurança

1. Enumerar a única coleção HID com VID:PID, strings, interface,
   usage e release exatos já conhecidos.
2. Fazer uma leitura ACP `0x00` e conferir identidade do firmware.
3. Fazer leitura ACP `0x8F`; exigir sete campos assinados,
   `wet` entre 0 e 100 e igualdade ao `--expect-wet` do operador.
4. Armar a sessão; fazer **segunda** leitura dos sete campos e
   cancelar se houver qualquer alteração entre as duas leituras.
5. Enviar uma única escrita `wet=atual±1` via HID
   `HidD_SetOutputReport`, depois `HidD_GetInputReport`.
6. Validar ACK estrito **e** ler novamente Chorus; exigir que
   os **seis outros campos** continuem idênticos ao início.
7. Em `finally`, tentar escrever **uma vez** o valor inicial
   de wet, mesmo que o ACK anterior ou readback tenham falhado.
8. Fazer readback de sete campos novamente; só declarar restauração
   confirmada se todos coincidirem com o estado inicial.
9. Fechar o handle em todos os caminhos normais de conclusão.

A leitura e a escrita nunca são emitidas a partir de
digitação parcial, sem botão Aplicar. Este CLI emite os dois
valores completos pré-validados.

## Interpretar o resultado

- `PASS_RESTORED`: ambos ACKs válidos, leitura candidata correta,
  e **todos os sete valores restaurados** por readback.
- `ERROR_BUT_RESTORED`: ocorreu falha, porém leitura final
  confirma os sete campos iguais aos originais. Não é aprovação M1F.
- `STATE_UNCERTAIN`: restauração não comprovada; nenhuma
  nova tentativa automática deve ocorrer.
- `REFUSED/FAILED` antes do início de escrita: versão,
  valor atual ou interface incompatíveis; não insistir.
- `TIMEOUT`: processo auxiliar interrompido. Mesmo com encerramento
  do handle Windows, **a restauração pode não ter ocorrido**.

**Limitação importante:** watchdog de processo não é transação atômica.
Se a USB desconectar ou o processo for terminado depois da escrita,
o DSP pode ficar com o valor temporário. Nessa situação, não
repetir automaticamente o teste: abrir ACPWorkbench **somente depois**
de confirmar que o processo auxiliar encerrou e verificar/restaurar
manualmente o valor de wet. Não gravar estado em flash.

O programa não mantém registro persistente de alteração,
nem habilita live sliders, controle de todos os 59 efeitos,
presets, UI com edição ou port ESP32-S3.

## Evidência de validação

A operação ao vivo do **novo** `probe_chorus_windows.py` ainda
não foi executada na BP1032 pelo proprietário nesta etapa.
Os testes sintéticos cobrem:
- empacotamento de byte-exato para candidato e restauração;
- ACK HID de 257 bytes, ID0 e preenchimento esperado;
- firmware divergente e wet desatualizado recusados;
- drift entre as duas leituras prévias recusado;
- ACK perdido após mudança física simulada;
- restauração com erro e desconexão durante readback final;
- alterações não esperadas em outros campos do Chorus;
- apenas uma alteração candidata e uma restauração.

A primeira confirmação real depende da saída do comando acima.

Links de referência:
- [`src/bpcontrol/usb_chorus_probe.py`](../src/bpcontrol/usb_chorus_probe.py)
- [`tools/probe_chorus_windows.py`](../tools/probe_chorus_windows.py)
- [`tests/test_chorus_probe.py`](../tests/test_chorus_probe.py)
- [`M1E_USB_ACK_CAPTURE.md`](M1E_USB_ACK_CAPTURE.md)
