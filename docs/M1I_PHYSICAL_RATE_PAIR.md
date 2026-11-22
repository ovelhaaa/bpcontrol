# M1I — par observado de Modulation Rate na BP1032

**Registro:** 2026-11-22. **Dispositivo:** BP1032 do operador, firmware consultado anteriormente `type 0x30 / v0.3.0 / biblioteca de efeitos 2.24.0`.

## Evidência obtida sem escrita

O operador enviou uma captura da interface **BPControl M1I · Chorus Evidence Inspector**, com a leitura de **Guitar Chorus** via USB em modo autorizado. A aba `Chorus · Evidências` mostra para o **campo 3 (Velocidade LFO)**:

- **`raw=200`**, origem **USB / leitura atual**;
- a interface também indica Chorus Wet `80`, coerente com a leitura inicial da M1H.

Na mesma mensagem, o operador informou que o **ACPWorkbench exibe `2,00 Hz`** no controle `Modulation Rate` do Chorus da placa.

**Par relatado e coerente:**

| Origem | Valor |
|---|---|
| Leitura BPControl USB HID, campo 3 do Guitar Chorus | `raw=200` |
| Valor apresentado no ACPWorkbench, informado pelo operador | `2,00 Hz` |
| Razão numérica correspondente a esse único ponto | `200 / 2,00 = 100 raw/Hz` |

**Interpretação:** o ponto `raw 200 ↔ 2,00 Hz` é **consistente com a escala `freq_Hz = raw/100` do firmware BP1032 instalado** e contradiz a interpretação `raw/10` se aplicada ao mesmo valor no mesmo momento. **Isso não determina a linearidade global**, passo mínimo, máximo permitido, comportamento de borda ou a frequência sonora realmente produzida pelo algoritmo.

Não foi fornecida uma segunda captura do ACPWorkbench na mesma mensagem; o valor exibido de `2,00 Hz` é **relato direto do operador**. A associação supõe que não houve alteração da configuração do Chorus entre as duas consultas. Se houver dúvida sobre a estabilidade do estado, uma nova comparação exclusivamente de leitura é suficiente.

## Diferença em relação à documentação BP1048

O manual ACPWorkbench inglês §6.1.27, o protocolo MVSilicon V2.40 §5.20.27 e o header `chorus.h` do SDK BP1048 descrevem parâmetros de rate com *décimos* de Hz (`raw 10↔1,0 Hz` no SDK), com faixa nominal raw `0..100`. A aplicação de exemplo BP1048 `communication.c` substitui uma escrita de rate acima de 100 pelo valor 10.

A leitura BP1032 `raw 200` e o display `2,00 Hz` não podem ser reconciliados mediante simples aplicação da escala `raw/10` daquele exemplo. **É evidência de diferenças na camada de apresentação, tradução ou implementação; não prova uma diferença binária específica ou o funcionamento do algoritmo sob o capô.** As versões das bibliotecas/firmwares também diferem e não são diretamente comparáveis.

## Decisão para o BPControl

- Apresentar **`2,00 Hz` apenas para `raw=200` como ponto observado**, qualificando-o claramente como correlação apresentada pelo operador, em vez de declarar uma fórmula validada para qualquer raw.
- Em outros valores: mostrar **raw** e a indicação **`escala fora do ponto medido pendente`**, sem estimativa extrapolada.
- Manter **campo 3, Modulation Rate, SOMENTE LEITURA**. Não habilitar `±1`, sliders, `SET_REPORT` ou alterações em lote para esse campo.
- **Única escrita permitida:** Guitar Chorus `0x8F`, campo 6 `wet`, com a proteção M1H já homologada (Apply explícito, ±1, readback e Undo).
- Não fazer gravação na flash (`0xFD`), atualização de firmware (`0xFE`) ou testes destrutivos.

## Evidência adicional ideal para calibrar a escala

O próximo passo, **se necessário**, seria observar um **segundo par de valores distintos** apresentados pelo ACPWorkbench e lidos via BPControl, sempre em programas separados, **sem escrita pelo BPControl**. Esse segundo ponto permitiria avaliar a linearidade candidata `raw/100`, mas **ainda não seria teste dos limites ou prova acústica da frequência do LFO**.

A captura original foi compartilhada na conversa e **não foi publicada no repositório**. Este arquivo preserva a proveniência textual e evita expor artefatos locais sem autorização explícita.
