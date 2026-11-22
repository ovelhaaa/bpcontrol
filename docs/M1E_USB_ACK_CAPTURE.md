# BPControl M1E — captura passiva de ACK de escrita do Chorus

**Estado:** ferramentas de captura e análise offline preparadas; nenhum comando de escrita ACP foi liberado no BPControl.

## Objetivo

Confirmar como o ACPWorkbench, pela interface HID `MI_04`, recebe a
resposta a uma alteração de **um único parâmetro** do Guitar Chorus:

- Instância ACP `0x8F` (15)
- Campo `6` (`wet`)
- Valor *atual da placa* lido no ACPWorkbench, **não presumido a partir do snapshot**
- Uma mudança de **1 unidade** e depois restauração explícita

Os logs ACPWorkbench anteriores exibem um ACK `8F` no nível da aplicação,
mas ainda não sabemos se o `GET_REPORT` USB devolve `8F 00...00`,
outro envelope, ou um formato diferente.

## Etapa A — Capturar (precisa de administrador no Windows)

Fechar outros programas BPControl que estejam acessando a interface HID.
Conectar a BP1032; deixar áudio mudo ou em volume baixo. Usar PowerShell
**como administrador** em `C:\progs\bpcontrol`:

```powershell
git pull
py tools/capture_usb_passive.py --scenario chorus-wet-ack --seconds 60 --output artifacts/usb-capture/chorus-wet-01.pcapng
```

O script identifica o USBPcap e o endereço atual da placa, recusa mapeamentos
ambíguos e encerra a captura dentro do tempo configurado. Ele **não abre
a interface HID da BP1032 para mandar comandos** e não manipula a GUI do
ACPWorkbench. Requer a instalação prévia do USBPcap, Wireshark e TShark
utilizada na etapa M1A.

**Durante a captura**, faça *manualmente* no ACPWorkbench:

1. Abrir Guitar Chorus e ler o `wet` atual; registrar o valor inicial.
2. Alterar `wet` em **1 ponto** (ex.: se for 80, usar 79).
3. Solicitar/observar um readback de Chorus; verificar o novo valor.
4. Voltar `wet` exatamente ao valor inicial (ex.: 80).
5. Solicitar/observar novo readback, confirmando o valor inicial.
6. Encerrar ACPWorkbench depois do teste; não executar flash save,
   firmware update, reset ou alterações de outros controles.

O nome `chorus-wet-01.pcapng` não pode existir antes da captura: o
script se recusa a sobrescrever. Se já existir, usar `chorus-wet-02.pcapng`.

**Não precisa necessariamente mudar de 80 para 79:** o valor **atual**
da placa pode diferir do snapshot antigo. Não use um valor presumido.

## Etapa B — Analisar totalmente offline

Após o fim da captura, no PowerShell (não exige administrador para análise):

```powershell
py tools/analyze_chorus_write_ack.py artifacts/usb-capture/chorus-wet-01.pcapng --output artifacts/usb-capture/chorus-wet-01-ack.json
```

O analisador reutiliza o parser USBPcap já validado. Ele:

- Localiza um endereço USB único com `SET_REPORT` exato para Chorus `0x8F`,
  campo `6`, `LEN=03`, `wIndex=4`, `wValue=0x0200`, payload de 256 B;
- Confere a sequência consecutiva `SET_REPORT` e `GET_REPORT` por
  endpoint, direção, stage, transaction, status e ausência de truncamento;
- Classifica um possível `GET_REPORT` cujo primeiro byte seja `8F`,
  seguido de **255 zeros**, como `bare_8f_zero_padded`;
- Mantém formatos desconhecidos como `unknown` ou `nonstandard_report_length`;
- Identifica leituras completas do Chorus presentes antes, durante e depois
  das alterações;
- Só considera uma restauração **observada** quando há readback do valor
  original depois da última escrita.

O relatório salva somente **a evidência necessária**: campos de setup,
números dos URBs relativos à captura, valores escritos, classificação e
primeiros 32 bytes dos ACKs candidatos, em JSON. O PCAP bruto fica local,
sob `artifacts/`, excluído do Git.

O analisador não transmite nenhum pacote, não abre HID, não grava
configurações e não instala drivers.

### Como interpretar

Exemplo hipotético, se o valor inicial real for 80:

```text
BPCONTROL M1E — PASSIVE CHORUS WRITE ACK INSPECTION (NO USB)
Found: 2 Chorus wet writes
Bare padded 0x8F candidate ACKs: 2
  SET packet ...: wet=79 ACK=bare_8f_zero_padded, GET packet=...
  SET packet ...: wet=80 ACK=bare_8f_zero_padded, GET packet=...
Pre-write baseline readback: 80
Final write matches baseline: True
Restoration readback in capture: True
```

**Isso é um exemplo**, não uma medição da sua captura. Se o analisador
reportar ACK desconhecido, não tiver readback inicial/final ou capturar
mais escritas que o esperado, **não repetir ou ativar escrita
automaticamente**. Compartilhar a saída textual para revisão.

## Limites da evidência

- Os bytes `8F` + zeros podem corresponder ao ACK esperado, mas uma
  confirmação segura exige também readback e restauração observada.
- O capturador registra URBs, não quadros elétricos USB.
- Report IDs de entrada/saída são zero nas leituras já capturadas; o
  resultado específico da escrita precisa ser observado.
- Os logs do ACPWorkbench já mostram escritas em aplicação, mas não
  comprovam seu encapsulamento USB.
- Nunca concluir que uma alteração foi restaurada apenas porque o último
  comando pede o valor inicial; precisa readback.
- Nenhum comando de escrita é autorizado no BPControl nesta fase.

## Depois da análise

Se a captura mostrar ACK, readback e restauração com valores corretos,
a próxima entrega será o teste **M1F**, limitado a um único campo
(`Guitar:Chorus wet`), com leitura inicial imediatamente antes,
alteração de ±1 ponto, ACK, readback, restauração e readback final.
Essa etapa deverá exigir autorização explícita e sinalizar rollback
incerto se ocorrer desconexão.

Arquivos:
- [`tools/capture_usb_passive.py`](../tools/capture_usb_passive.py)
- [`tools/analyze_chorus_write_ack.py`](../tools/analyze_chorus_write_ack.py)
- [`tests/test_chorus_write_ack.py`](../tests/test_chorus_write_ack.py)
- [`M1E_FIRST_WRITE_PREPARATION.md`](M1E_FIRST_WRITE_PREPARATION.md)
