# BPControl M1K-B — Probe físico supervisionado do Harmonic Exciter (`0x9D`)

## Objetivo

Executar a primeira escrita reversível supervisionada no **Harmonic Exciter (`0x9D`)** da BP1032 (firmware `0.3.0`, effects library `2.24.0`), com base na evidência passiva **M1K-A** (`exciter-01-ack.json`), preservando:

- Allowlist estrita (`0x00` firmware + `0x9D` Exciter apenas).
- Double readback de pré-flight dos 4 campos (`enable`, `cutoff`, `dry`, `wet`) antes de qualquer escrita.
- Apenas **uma** alteração pequena e reversível por execução:
  - `wet` (campo 3): `±1` dentro de `0..100`
  - `dry` (campo 2): `±1` dentro de `0..100`
  - `cutoff` (campo 1): `±100 Hz` dentro de `1000..10000 Hz`
- Validação exata do ACK HID (`ID=0 + 0x9D + 255 bytes zero`).
- Readback de confirmação, uma única tentativa de restauração e readback final dos 4 campos.
- Timeout de `15 s` no processo filho, zero retries automáticos e proibição de gravação na flash (`0xFD`).

## Arquivos

- [`src/bpcontrol/usb_exciter_probe.py`](../src/bpcontrol/usb_exciter_probe.py)
- [`tools/probe_exciter_windows.py`](../tools/probe_exciter_windows.py)
- [`tests/test_exciter_probe.py`](../tests/test_exciter_probe.py)

## Procedimento operacional PowerShell (validação física)

> **Pré-requisitos:** Feche o **ACPWorkbench** e mantenha o áudio em volume baixo/mutado. Nunca execute com o ACPWorkbench aberto.

1. Consulte o estado atual do Exciter (somente leitura) com o M1J Inspector ou confirme os valores atuais (`wet`, `dry`, `cutoff`).
2. Execute **um campo por vez**, passando o valor atual exato em `--expect-value`:

```powershell
# Exemplo 1: testar wet (assumindo wet atual = 100)
py tools/probe_exciter_windows.py --live-exciter-probe --field wet --expect-value 100 --authorize-one-temporary-write

# Exemplo 2: testar dry (assumindo dry atual = 100)
py tools/probe_exciter_windows.py --live-exciter-probe --field dry --expect-value 100 --authorize-one-temporary-write

# Exemplo 3: testar cutoff (assumindo cutoff atual = 1000)
py tools/probe_exciter_windows.py --live-exciter-probe --field cutoff --expect-value 1000 --authorize-one-temporary-write
```

3. Resultado esperado: `status = "PASS_RESTORED"`, `candidate_ack_valid = true`, `restoration_ack_valid = true`, `restoration_verified = true` e `PASS: single temporary Exciter write was ACKed/read back; all 4 Exciter fields restored and verified.`
4. Se ocorrer `TIMEOUT` ou `STATE_UNCERTAIN`, **não repita automaticamente**; abra o ACPWorkbench e verifique/restaure manualmente.

## Validação física confirmada (2026-11-24)

O operador executou os três probes na placa física **BP1032** (firmware `0.3.0`, effects library `2.24.0`), todos com **`PASS_RESTORED`**, ACKs válidos e restauração completa dos 4 campos:

| Campo | Baseline | Candidato | Readback candidato | Readback restauração | Resultado |
|---|---|---|---|---|---|
| `wet` (3) | `[0, 1000, 100, 100]` | `99` | `[0, 1000, 100, 99]` | `[0, 1000, 100, 100]` | `PASS_RESTORED` |
| `dry` (2) | `[0, 1000, 100, 100]` | `99` | `[0, 1000, 99, 100]` | `[0, 1000, 100, 100]` | `PASS_RESTORED` |
| `cutoff` (1) | `[0, 1000, 100, 100]` | `1100` | `[0, 1100, 100, 100]` | `[0, 1000, 100, 100]` | `PASS_RESTORED` |

Nenhum comando de gravação em flash (`0xFD`) foi enviado.

