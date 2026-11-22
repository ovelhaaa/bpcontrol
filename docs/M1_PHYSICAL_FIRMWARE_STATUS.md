# BP1032 M1A — leituras físicas de firmware e status

Data: 2026-11-22. Proveniência: saídas de terminal informadas pelo proprietário após
execução de consultas ACP **somente de leitura** com ACPWorkbench fechado, pela
interface HID MI_04 da BP1032. Não foram realizados comandos de escrita de
parâmetros, persistência em flash nem atualização de firmware por essas consultas.

## Firmware — comando ACP 0x00

```text
READ OK: firmware command=0x00
raw_payload_hex: 30 00 03 00 02 18 00
payload_bytes: 7
```

Decodificação conforme o protocolo MVSilicon V2.40.0, §5.1:

| Bytes | Significado | Valor |
|---|---|---|
| `30` | Tipo de firmware | `0x30`, BPxx AudioPlay SDK |
| `00 03 00` | Versão do firmware | `0.3.0` |
| `02 18 00` | Versão da biblioteca de efeitos | `2.24.0` |

O tipo `0x30` identifica a **família de firmware**, não o modelo exato do chip.

## Sistema — comando ACP 0x02

```text
READ OK: status command=0x02
raw_payload_hex: FF 46 00 1A 00 00 40 01 40 01
payload_bytes: 10
```

Decodificação conforme o protocolo MVSilicon V2.40.0, §5.3:

| Offset na carga | Bytes | Campo | Valor |
|---|---|---|---|
| 0 | `FF` | Marcador | `0xFF` |
| 1–2 | `46 00` | Memória ocupada (KB, u16 LE) | 70 KB |
| 3–4 | `1A 00` | CPU Usage (u16 LE) | 26 |
| 5 | `00` | Indicador de alteração externa | 0 (não) |
| 6–7 | `40 01` | Frequência máxima da CPU (MHz, u16 LE) | 320 MHz |
| 8–9 | `40 01` | Memória máxima (KB, u16 LE) | 320 KB |

**Unidade da CPU esclarecida:** o protocolo V2.40.0 §5.3 chama este campo
`CPU Usage` sem explicitar a unidade; porém o manual oficial
`ACPWorkbench-ENG.pdf` v2.25.0, §8.1 (página 33) especifica
`MCPS` = **mega cycles per second**. O proprietário observou `26` na UI
do ACPWorkbench; portanto `26 MCPS` é a interpretação documentada mais
forte. **MCPS não significa MIPS** (milhões de instruções/s). Não substituir
automaticamente as duas unidades.

**Capacidade nominal relativa:** `26 MCPS / 320 MHz = 8.125%` dos
320 milhões de ciclos por segundo correspondentes à frequência máxima
reportada. Este é apenas um **índice relativo ao máximo nominal**, e não
uma medida garantida da ocupação instantânea da CPU, da frequência
de operação real ou do custo de um efeito isolado.

**Memória:** `70 / 320 = 21.875%` da capacidade máxima informada pelo
próprio dispositivo. O manual ACPWorkbench antigo cita outras faixas
de RAM para outras placas; usar os limites lidos deste hardware.

## Marcos e próximos passos

- [x] Leitura física de Chorus `0x8F` com parâmetros decodificados.
- [x] Leitura física de firmware `0x00` com versão consistente.
- [x] Leitura física de status `0x02` com valores parseados.
- [x] Identificação da unidade MCPS no manual do ACPWorkbench.
- [ ] Habilitar catálogo de leituras de efeitos observado (59 instâncias), com mapeamento e detecção de versão.
- [ ] Adicionar telemetria opcional de baixa frequência, limite de carga e tratamento de desconexão, após testes de estabilidade.
- [ ] Só depois: escrita de parâmetros validada, com autorização explícita e readback; não enviar `0xFD` nem `0xFE`.

As ferramentas atuais `tools/read_info_windows.py` e `tools/read_chorus_windows.py`
executam uma consulta por invocação; não há repetição automática.

Referências locais originais (não versionar PDFs proprietários no repositório):
- `固件与用户应用程序通信协议V2.40.0.pdf`, seções 5.1 e 5.3.
- `ACPWorkbench-ENG.pdf` v2.25.0, seção 8.1, página 33.
