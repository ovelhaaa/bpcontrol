# BPControl M1I — reavaliação do manual ACPWorkbench e evidências do Chorus

## Origem desta revisão

O operador pediu uma segunda análise de um dos arquivos de referência.
Reexaminamos o **ACPWorkbench-ENG.pdf**, particularmente a página 27,
seção **6.1.27 Chorus**, e confrontamos o conteúdo com:

- O `ACPWorkbench.ini` fornecido, seção `[0x8f-Chorus]`;
- O log ACPWorkbench original `Texto colado(20261122-010029).txt`
  de operações ACP / USB, incluindo escrita de field 3 raw 0 e 100;
- O baseline físico da M1F, `[1, 20, 10, 200, 50, 80, 80]`;
- A M1H, que validou wet `80→81→80` por ACK/readback
  e consulta USB fresca `80`;
- O esquema `src/bpcontrol/effects.py`, que havia rotulado
  `modulation_rate` como `centiHz`;
- A descrição anterior em `docs/ACP_PROTOCOL.md`, que dizia
  `100→1,00Hz`.

Os arquivos PDF/INI e o log de ACPWorkbench são **observações de
origem diferente**. Um valor padrão no INI não prova o valor
atual de uma placa. Um limite de manual genérico não prova que uma
determinada firmware usa o mesmo limite e escala.

## Faixas publicadas no manual, §6.1.27

| Campo ACP | Nome | Faixa segundo o manual | Restrições da M1I |
|---|---|---|---|
| 0 | Enable | Flag 0/1 por esquema | Somente leitura; manual §6.1.27 não define faixa |
| 1 | Delay Length | 1–25 ms | Somente leitura; valores extremos não ensaiados |
| 2 | Modulation Depth | 0 até `delay_length−1` ms | Somente leitura; restrição relativa documentada |
| 3 | Modulation Rate | 0–10 Hz, passo de 0,1 Hz | **Somente leitura; discrepância de escala e faixa** |
| 4 | Feedback | 0–50% | Somente leitura |
| 5 | Dry | 0–100% | Somente leitura |
| 6 | Wet | 0–100% | Único gravável no backend existente, ±1 por confirmação |

As faixas do manual tornam o UI mais útil, mas não são permissão
para comandos adicionais. Os valores brutos permanecem
visíveis e são comparados com o snapshot e o readback real.

## Divergência crítica: Modulation Rate

O manual diz literalmente, na seção 6.1.27, que o campo se expressa
em décimos de Hz:

```text
raw 2   => 0.2 Hz
raw 10  => 1.0 Hz
raw 100 => 10.0 Hz
faixa nominal: 0.0..10.0 Hz, passo 0.1 Hz
```

Mas os outros registros fornecem dados diferentes:

1. O `ACPWorkbench.ini` tem `modulation_rate=10` na
   instância `0x8f-Chorus`, consistente com **1,0 Hz** sob o manual.
   **Isso é valor inicial de configuração**, não leitura física.
2. O log ACPWorkbench fornecido registra um `SET_REPORT`
   `A5 5A 8F 03 03 64 00 16` seguido por resposta/ACK e
   readback de `raw=100` no campo 3. Isso comprova o valor
   bruto transmitido, mas **não registra, nesse pacote, o Hz
   exibido na interface**.
3. Uma anotação anterior do BPControl apontava
   `raw100=1,00Hz`, isto é, escala `raw/100`.
4. O baseline físico BP1032 da M1F registra
   **`raw=200`** no mesmo campo, superior ao limite de 100
   que o manual descreve para `raw/10`.
5. O JSON `data/effects.json` herdara `scale=100`,
   promovendo uma hipótese a valor definitivo.

**Conclusão:** nenhuma das conversões `raw/10` ou `raw/100`
pode ser promovida hoje à escala absoluta real da firmware
HunXiang_F sem observar a leitura do número no ACPWorkbench
**lado a lado** com o raw e conferir a versão do software.

A M1I:
- mudou o esquema Chorus field 3 para unidade **raw** e
  evidência **inferida**, em vez de `centiHz`;
- retirou a conversão definitiva de `data/effects.json`,
  marcando as duas hipóteses e a observação raw 200;
- atualizou `docs/ACP_PROTOCOL.md` para registrar a discrepância;
- apresenta o campo 3 com **CONFLITO DE ESCALA**, nunca
  com uma conversão inventada para Hz;
- mantém **field 3 bloqueado** para escrita.

## Nova aba M1I — evidências sem USB adicional

O script habitual `tools/chorus_editor_gui.py` agora oferece
a aba **Chorus · Evidências**, independente da aba de atividade.
A nova aba mostra, para cada um dos sete campos:

- Nome, índice, bruto salvo e bruto lido atualmente;
- Fonte do valor: snapshot vs consulta USB real;
- Faixa descrita no manual, inclusive a dependência entre
  `modulation_depth` e `delay_length`;
- Observações e conflitos;
- Permissão atual de escrita (somente wet);
- Referências documentais e motivo pelo qual a escala
  ainda pode estar pendente.

A aba é **estritamente somente leitura**.
Não há botões Apply nem novos dispositivos/endpoints,
e a consulta manual Chorus usa exatamente o worker M1H.
Outros efeitos seguem apenas com valores do snapshot.

## Como validar sem tocar na placa

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

Abra **Guitar Chorus → Chorus · Evidências** e confira os sete
campos, a faixa documentada, as fontes e a marcação de
`Modulation Rate: CONFLITO DE ESCALA`. Esse teste não acessa
HID/USB nem altera DSP. O layout corrigido da M1H conserva
o editor wet acima da tabela.

## Próxima evidência útil — somente leitura

Para resolver a escala do Modulation Rate, preferir uma
observação não invasiva em duas etapas **sem abrir dois
controladores USB simultaneamente**:

1. Com BPControl fechado, abrir o ACPWorkbench, selecionar
   o Guitar Chorus, fazer uma **leitura dos valores atuais**,
   anotar ou capturar tela do número exibido em
   Modulation Rate, junto com versão do ACPWorkbench;
   **não modificar nem salvar** qualquer parâmetro.
2. Fechar ACPWorkbench. Abrir BPControl com
   `--enable-live-writes`, pressionar apenas
   **Consultar Chorus (USB)** e anotar o `field 3 raw`
   mostrado na aba de evidências. Não clicar
   Apply, Undo ou ±1 nesta investigação.

Se o ACPWorkbench exibir, para o mesmo `raw=200`, por exemplo
`2,00 Hz`, isso apoiaria `raw/100`; se exibir `20,0 Hz`,
apoiaria `raw/10` mas revelaria um limite físico maior que o
manual. **Esses números são cenários ilustrativos, não
resultados já observados.**

Se o valor bruto mudar entre as duas observações, os dados não
formam um par comparável. Não supor escala com dados
desencontrados. Só depois dessa checagem é possível desenhar
um controle de LFO com unidades musicais confiáveis.

## Outros achados úteis do mesmo manual

O manual inglês §6.1.30 descreve o argumento **interno** do
Ping Pong em amostras, mas o protocolo chinês V2.40 §5.20.30
documenta o valor **ACP em milissegundos** (padrão 250 ms).
O firmware de exemplo BP1048 em `ctrlvars.c` converte explicitamente
`delay_samples = delay_ms * sample_rate / 1000` (idem max delay).
São **camadas diferentes**, não uma razão para trocar a unidade
do comando ACP para amostras. As seções 6.1 de vários outros efeitos
podem servir para futuras abas **read-only** de intervalo e
unidades, sem presumir que os 59 slots correspondem a 59
algoritmos diferentes ou que compartilham todas as faixas
da mesma versão de firmware.

## Critérios e limites

- M1H: escrito/testado fisicamente apenas Guitar Chorus
  field6 (wet), uma unidade por confirmação.
- M1I: inspeção de metadados offline, com fonte e conflito
  explícitos, **sem ampliação da allowlist HID**.
- O backend existente exige firmware, duas leituras prévias,
  comparação dos sete campos e confirmação do usuário
  antes da escrita de wet. Nenhuma nova saída de escrita
  foi adicionada nessa etapa.
- Nenhum `0xFD` (flash-save), `0xFE` (firmware),
  reset, MIDI ou polling automático.
- Testes automatizados podem verificar esquema e interface
  sem demonstrar que as escalas contraditórias estão resolvidas.

Arquivos:
- [`src/bpcontrol/chorus_evidence.py`](../src/bpcontrol/chorus_evidence.py)
- [`src/bpcontrol/effects.py`](../src/bpcontrol/effects.py)
- [`tools/chorus_editor_gui.py`](../tools/chorus_editor_gui.py)
- [`tests/test_chorus_evidence.py`](../tests/test_chorus_evidence.py)
- [`docs/ACP_PROTOCOL.md`](ACP_PROTOCOL.md)
- [`docs/ROADMAP.md`](ROADMAP.md)


## Evidência complementar: protocolo V2.40 + SDK BP1048 + adaptação ESP32

Ver [M1I_PROTOCOL_SDK_CROSSCHECK.md](M1I_PROTOCOL_SDK_CROSSCHECK.md).
O header `chorus.h` do SDK BP1048 confirma `raw/10` para a API DSP;
a aplicação de exemplo `communication.c` limita escritas rate acima
de 100 ao default 10. A BP1032 já foi lida em raw=200, o que mantém
a escala da firmware física **não comprovada**. O parâmetro continua
somente leitura. O SDK `pingpong.h` recebe samples internamente,
enquanto a aplicação traduz ms ACP para samples no próprio firmware.
