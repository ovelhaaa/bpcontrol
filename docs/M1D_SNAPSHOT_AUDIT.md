# M1D — Auditoria do snapshot real dos 59 efeitos (offline)

## Estado

O operador relatou em 2026-11-22 que a leitura em lote do BPControl e a
interface HTML **funcionaram perfeitamente** no Windows com a BP1032 física.
Esta confirmação é um relato do usuário. O arquivo JSON real permanece
local e **ainda não foi inspecionado nesta revisão do repositório**;
portanto não afirmamos independentemente que todos os 59 readbacks tenham
contagem, escala e nomenclatura validadas.

O M1D não precisa abrir ACPWorkbench, refazer a captura ou enviar qualquer
comando USB. Audita o `artifacts/snapshots/bp1032-01.json` já existente.

## Como executar

No PowerShell, dentro de `C:\progs\bpcontrol`:

```powershell
git pull
py -m unittest discover -s tests -v

# Resumo com contagens, alertas e divergências:
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json

# Tabela das 59 instâncias:
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json --table

# Relatório completo em JSON, também sem USB:
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json --json > artifacts/snapshots/bp1032-01-audit.json
```

A ferramenta não modifica o snapshot e não executa qualquer `SET_REPORT` ou
`GET_REPORT`. `--json` produz relatório offline para arquivo via
redirecionamento do PowerShell. O auditor retorna código 1 se detectar erros
estruturais graves; alertas de nomenclatura/contagem não têm o mesmo nível de
severidade.

Se o arquivo se chamar `bp1032-02.json`, substitua o nome nas três linhas.
Não rode outra consulta USB sem necessidade.

## O que é verificado

**Integridade técnica (erro):**
- `format=bpcontrol-snapshot-v1` e exatamente 59 posições;
- IDs sequenciais `1..59`, comandos `0x81..0xBB`;
- família `0x30`, firmware `0.3.0`, efeitos `2.24.0` compatíveis com
  o catálogo de nomes do INI original;
- quantidade declarada de leituras e `complete` coerentes;
- cada valor `signed` e `unsigned` corresponde ao mesmo inteiro de 16 bits;
- bytes do `raw_payload_hex` batem **exatamente** com os valores dos campos;
- payload contém marcador `FF`, tamanho coerente e no máximo 125 palavras
  de 16 bits por quadro ACP em 256 bytes.

**Análise de mapeamento (alerta):**
- número de campos observados versus quantidades sugeridas pelo INI;
- coincidência de campos com os seis esquemas estudados;
- nomes do snapshot divergentes das referências do INI;
- efeitos ainda não lidos ou com erro;
- campos com mapeamento originalmente inferido — principalmente Pro Reverb.

O relatório `--table` classifica cada instância:
- `known_schema`: a contagem coincide com um dos seis esquemas conhecidos;
- `known_schema_with_inference`: corresponde a esquema conhecido que contém
  nomes de campos **inferidos**, sem comprovação individual;
- `raw_only`: a leitura ACP foi interpretada estruturalmente, mas seus
  parâmetros seguem como `field_NN` e nomes do INI são apenas dicas;
- `not_read`: a instância não contém readback válido.

**Importante:** `known_schema` **não é autorização de escrita**, não comprova
a faixa de valores e não garante que um campo tenha sido associado ao
controle correto em todas as versões da biblioteca.

## Resultados esperados: como interpretar

O relatório ideal de captura mostra `Read successfully: 59/59`,
`Unread: 0` e `Audit errors: 0`. Podem existir avisos de
`ini_count_mismatch`; isso indica uma discrepância a pesquisar, não
necessariamente um bug no firmware.

Mesmo que a análise estrutural passe, os valores de frequência, ganho,
tempo e coeficientes de EQ precisam de validação adicional antes de usar
sliders de controle, especialmente com campos `Q6.10`, `Q8.8`,
`Q15` ou enumerações.

Como não temos ainda o JSON físico aqui, **nenhuma divergência específica
entre os 59 readbacks reais e o INI foi confirmada**. O código não fabrica
essa conclusão.

## Plano de entrada para M1E — controles seguros

1. Analisar primeiro os resultados do auditor das instâncias:
   `0x8A` Mic Echo, `0x8D` Mic Pro Reverb, `0x8E` Guitar PingPong,
   `0x8F` Guitar Chorus, `0x94` Pitch Shifter Pro, `0x9C` Music Delay.
2. Corrigir mapeamentos e escalas a partir de evidência independente
   (documentação de protocolo, capturas originais ACPWorkbench e
   readbacks reproduzíveis), sem derivar semântica exclusivamente
   da ordenação do INI.
3. Introduzir um estado de *readiness* por parâmetro:
   `read_only`, `candidate`, `verified_for_write`.
   A primeira etapa permanece `read_only` para todos.
4. Testar eventualmente **uma** alteração não persistente, de um
   parâmetro conhecido e reversível, com autorização explícita, coleta do
   estado anterior, confirmação de leitura pós-escrita e rollback. Não usar
   `0xFD`, `0xFE`, reset ou escrita em parâmetros desconhecidos.
5. O futuro editor em tempo real deverá tratar desconexão, aplicação
   pendente, readback não coincidente e exclusividade com ACPWorkbench.

## Testes de regressão

`tests/test_audit_snapshot.py` cobre fixture de demonstração
(1 instância lida/58 não lidas), uma fotografia **sintética** de 59
instâncias (não representa o hardware), corrupção do campo de 16 bits,
mudanças indevidas de comando, alteração de versão de firmware,
dissonância entre bytes ACP e JSON e captura interrompida.

Estas verificações, mesmo com GitHub Actions passando, **não substituem
a auditoria do arquivo real do proprietário**.

Arquivos principais:
- [`tools/audit_snapshot.py`](../tools/audit_snapshot.py)
- [`data/effect_instances.json`](../data/effect_instances.json)
- [`src/bpcontrol/snapshot.py`](../src/bpcontrol/snapshot.py)
- [`tests/test_audit_snapshot.py`](../tests/test_audit_snapshot.py)

## Physical M1D audit: operator-reported results (2026-11-22)

The owner subsequently pasted terminal output for the actual Windows
BP1032 snapshot. It reported:

```text
Snapshot marked complete: True
Read successfully: 59/59  (declared: 59)
Unread: 0  capture errors: 0
Raw signed/unsigned fields: 845
Known evidence-graded schema mappings: 6/6
Instances with raw-only labels: 53
Count mismatches vs INI hints: 0
Audit errors: 0  warnings: 0
```

The entire 59-row table showed that every instance's readback word count
matches the INI hint count; the largest schemas were 79 words for `0xAA`
and `0xAB`, followed by 53 words for the eight EQ instances. Pro Reverb
has 17 words but some field labels are still inferred. This evidence
comes from **the operator's displayed audit output**, not independent
inspection of the unshared raw JSON bytes. It does not validate each
field's scale or authorize writes.

The next step is [M1E write preparation](M1E_FIRST_WRITE_PREPARATION.md),
starting with an offline candidate frame and a passive ACPWorkbench HID
write/ACK capture before any BPControl-controlled parameter changes.
