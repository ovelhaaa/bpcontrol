# BPControl M1K-A — Harmonic Exciter (`0x9D`) Protocol Evidence

## Contexto confirmado

- Hardware físico: **BP1032**, firmware `0.3.0`, effects library `2.24.0`.
- **M1J Music FX Inspector validado pelo operador**: as leituras físicas somente leitura dos quatro efeitos Music (`0x97`, `0x98`, `0x9B`, `0x9D`) funcionaram corretamente.
- O editor **Chorus wet (`0x8F` campo 6)** permanece preservado e sem regressões.
- O operador observou no **ACPWorkbench** que o valor mínimo aparente de `cutoff` do Exciter é **1000 Hz**, consistente com o SDK BP1048 (`exciter.h`), mas divergente do mínimo de **300 Hz** especificado no protocolo ACP V2.40.
- Essa observação é mantida estritamente como **evidência física reportada**, não como comprovação universal de todos os limites ou de outros firmwares.

## 1. Auditoria de schema: ACP V2.40 vs SDK BP1048 vs BP1032

Instância observada em `data/effect_instances.json`:
- Índice: `29` (`Music:Music Exciter`)
- Comando ACP: `0x9D`
- Tipo: `25` (`Harmonic_Exciter`)

| Campo | Chave | ACP V2.40 §5.20.26 | SDK BP1048 (`exciter.h` / `audio_effect.c`) | Evidência / Observação BP1032 | Permissão atual |
|---:|---|---|---|---|---|
| 0 | `enable` | `0 / 1` | `0 / 1` | Leitura M1J validada | Somente leitura |
| 1 | `cutoff_frequency` | `300–10000 Hz` | `1000–10000 Hz` | Operador observou mínimo aparente `1000 Hz` no ACPWorkbench | Somente leitura |
| 2 | `dry` | `0–100 %` | `0–100 %` | Leitura M1J validada | Somente leitura |
| 3 | `wet` | `0–100 %` | `0–100 %` | Leitura M1J validada | Somente leitura |

Implementação auditada em [`src/bpcontrol/exciter_evidence.py`](../src/bpcontrol/exciter_evidence.py) e [`src/bpcontrol/music_effects.py`](../src/bpcontrol/music_effects.py).

## 2. Procedimento operacional PowerShell — Captura USBPcap passiva

> **Pré-requisitos:** Feche todas as ferramentas HID do BPControl antes de capturar. Nunca conecte ACPWorkbench e BPControl simultaneamente. Não grave na flash (`0xFD`) nem atualize firmware (`0xFE`).

Em um **PowerShell como Administrador**, na pasta `C:\progs\bpcontrol`:

```powershell
git pull
py -m pip install -e .
py tools/capture_usb_passive.py --scenario exciter-ack --seconds 90 --output artifacts/usb-capture/exciter-01.pcapng
```

Durante a janela de captura, no **ACPWorkbench**:
1. Leia o estado atual do **Music Exciter (`0x9D`)** (baseline pré-escrita).
2. Faça alterações **isoladas, um campo por vez**, lendo após cada mudança e restaurando em seguida:
   - Altere **cutoff** (ex.: +100 Hz) → leia/confirme → restaure ao valor original → leia/confirme.
   - Altere **dry** (ex.: ±1 ou ±5 %) → leia/confirme → restaure ao valor original → leia/confirme.
   - Altere **wet** (ex.: ±1 ou ±5 %) → leia/confirme → restaure ao valor original → leia/confirme.
3. Não clique em Save/Flash e não altere outros efeitos.

Ao término da captura, execute a análise **offline** (em PowerShell normal, sem acesso USB):

```powershell
py tools/analyze_exciter_write_ack.py artifacts/usb-capture/exciter-01.pcapng --output artifacts/usb-capture/exciter-01-ack.json
```

O analisador offline:
- Associa `SET_REPORT` (`0x21 0x09 0x0200 wIndex=4 wLength=256`), `GET_REPORT` (`0xA1 0x01 0x0100 wIndex=4 wLength=256`), forma do ACK (`bare_9d_zero_padded`, `candidate_full_acp_frame`, `unknown`) e readbacks por campo.
- Exige baseline obtido de um readback **anterior** à primeira escrita.
- Verifica restauração por campo e globalmente, recusando confirmar rollback se faltar baseline, readback final ou se houver divergência de valores.
- Sinaliza pacotes inválidos, ausência de ACK, respostas fora de ordem/intercaladas e escritas duplicadas.

## 3. Protótipo offline de editor staged do Exciter

- [`src/bpcontrol/exciter_editor.py`](../src/bpcontrol/exciter_editor.py) e [`tools/exciter_editor_gui.py`](../tools/exciter_editor_gui.py).
- **100% offline**: `EXCITER_LIVE_WRITE_ENABLED = False`, zero imports de módulos USB/HID, sem sliders contínuos, apenas rascunho numérico local (`Stage Offline` / `Desfazer Stage`) e pré-visualização hexadecimal de quadro ACP `0x9D`.

Abrir offline:

```powershell
py tools/exciter_editor_gui.py
```

## 4. Limitações e itens explicitamente fora de escopo (M1K-A)

- **Não implementado:** live writes de Exciter (`0x9D`), Music 3D (`0x97`), 3D Plus (`0x98`) ou Stereo Widener (`0x9B`).
- **Não implementado:** sliders com envio contínuo por USB.
- **Preservado:** allowlist estrita de comandos, identificação estrita do dispositivo, comportamento fail-closed, ausência de retries automáticos e proibição de gravação na flash.
