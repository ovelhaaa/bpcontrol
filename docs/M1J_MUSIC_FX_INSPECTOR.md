# BPControl M1J — Music FX Inspector

## Objetivo

O proprietário confirmou que o áudio reproduzido via USB pela BP1032 é
afetado pela cadeia Music. A M1J fornece um **inspetor independente e
somente leitura**, com valores salvos e leitura USB manual dos efeitos
3D, 3D Plus, Stereo Widener e Harmonic Exciter. Preserva integralmente o
editor do Chorus wet, já validado na placa física.

O inspetor NÃO reproduz nem monitora áudio: esta etapa prepara a
observação de parâmetros para complementar o loopback USB Audio que
já funciona no Windows.

## Instâncias da firmware física

| Instância | Comando ACP | Tipo do catálogo | Campos (índices) |
|---|---|---|---|
| 23 / Music 3D | 0x97 | 12 / MV3D | enable 0, intensity 1 |
| 24 / Music 3D Plus | 0x98 | 30 / MV3D_Plus | enable 0, intensity 1 |
| 27 / Music Stereo Winden (nome no INI) | 0x9B | 28 / Stereo_Widener | enable 0, shaping 1 |
| 29 / Music Exciter | 0x9D | 25 / Harmonic_Exciter | enable 0, cutoff 1, dry 2, wet 3 |

Fonte: data/effect_instances.json, extraído do ACPWorkbench.ini e validado
contra o catálogo das 59 instâncias do firmware 0.3.0 / effects 2.24.0.
Os índices são ESPECÍFICOS da firmware observada; outros firmwares
podem ter tipos e posições diferentes.

## Faixas documentadas (não ensaiadas nos extremos da BP1032)

- MV3D e MV3D Plus: intensidade 0 a 100%, protocolo V2.40 §§5.20.13 e
  5.20.31. Não possuem um width separado nesse protocolo.
- Stereo Widener: shaping binário (0 sem shaping; 1 com shaping).
  O SDK BP1048 stereo_widener.h confirma o parâmetro e documenta
  processamento estéreo; NÃO há ajuste contínuo de largura.
- Harmonic Exciter: dry/wet 0 a 100%; cutoff tem **DIVERGÊNCIA**:
  protocolo V2.40 §5.20.26 diz 300 a 10000 Hz, enquanto o SDK BP1048
  exciter.h define mínimo de 1000 Hz e máximo de 10000 Hz.
  O operador observou no ACPWorkbench (BP1032 fw 0.3.0 / lib 2.24.0) que o
  cutoff mínimo aparentemente é **1000 Hz**, consistente com o SDK BP1048.
  Manter como **evidência física reportada**, não como comprovação de todos
  os limites ou de outros firmwares.

Referências do SDK:
- https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/master/MVsB1_Base_SDK/middleware/audio/inc/stereo_widener.h
- https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/master/MVsB1_Base_SDK/middleware/audio/inc/exciter.h

## Arquivos novos

- src/bpcontrol/music_effects.py: metadados, quatro comandos de leitura
  fixos, verificação estrita da contagem de palavras raw por efeito,
  modelos de evidência e origem dos valores.
- tools/music_read_worker.py: consulta o firmware 0x00, verifica
  identidade BP1032 observada e emite APENAS quatro leituras:
  0x97, 0x98, 0x9B, 0x9D. Nenhuma escrita de parâmetro.
- tools/music_inspector_gui.py: janela Tkinter Music FX com
  seleção de efeito, tabela de campos e limites, notas para audição,
  botão de consulta USB, timeout de 15 s no processo filho, sem retries.
- tests/test_music_effects.py e tests/test_music_inspector_gui.py:
  testes offline de identificadores, bytes, limites documentais,
  validação de respostas, retorno USB e comportamento fail-closed.

**Sem escrita, sem gravação na flash, sem atualização de firmware,
sem polling e sem qualquer configuração de áudio automática.**

## Abrir offline sem tocar na BP1032

Em PowerShell na pasta C:\progs\bpcontrol:

    git pull
    py -m pip install -e .
    py -m unittest discover -s tests -v
    py tools/music_inspector_gui.py

Nenhum USB é acessado ao iniciar ou trocar os quatro efeitos.
Os valores são do snapshot local quando disponível, ou permanecem
vazios se o snapshot demo não contiver leituras.

## Primeira leitura física, opcional

Com a BP1032 conectada e o ACPWorkbench **FECHADO**:

    py tools/music_inspector_gui.py --enable-live-reads

1. Clique CONSUL​TAR 4 EFEITOS (USB) uma única vez.
2. Confira se a barra informa que os quatro efeitos foram lidos.
3. Escolha Music 3D, Music 3D Plus, Stereo Widener e Exciter.
4. Os campos devem aparecer com origem USB atual. Anote os valores
   e compare com os parâmetros que o ACPWorkbench exibia antes.
5. Não é possível aplicar, desfazer ou salvar parâmetros a partir
   dessa tela. Falhas recusam a leitura como um todo.

É permitido manter a reprodução USB Audio do Windows para escutar
a cadeia Music, mas o programa não assume que todo sinal de gravação
USB seja necessariamente pós-DSP; isso foi testado na instalação
do operador, não é uma garantia universal de hardware.

## Comparação auditiva recomendada

Reproduzir sempre a mesma amostra WAV estéreo e, quando possível,
ativar um efeito Music por vez no ACPWorkbench, fechando o ACPWorkbench
antes de consultar os valores no BPControl.

- 3D e 3D Plus: comparar profundidade e imagem central com o mesmo
  volume percebido, além de verificar compatibilidade mono.
- Stereo Widener: comparar shaping 0 e 1 e eventuais mudanças
  de correlação estéreo e cancelamentos ao somar em mono.
- Harmonic Exciter: usar material harmônico e ouvir ganho aparente,
  nitidez ou aspereza dos agudos. Começar com volume baixo.

Os atributos acústicos são hipóteses para AUDIÇÃO, não descrições
comprovadas da implementação binária BP1032.

## Próxima etapa recomendada

**M1J (validado fisicamente pelo operador em 2026-11-22):** as quatro
leituras físicas somente leitura (`0x97`, `0x98`, `0x9B`, `0x9D`)
funcionaram corretamente na BP1032 (fw 0.3.0 / effects lib 2.24.0).

**M1K-A (em andamento):** capturar no USBPcap passivo as alterações
isoladas do ACPWorkbench para o Harmonic Exciter (`0x9D`: `cutoff`, `dry`,
`wet`) e seus ACK/readbacks offline antes de avaliar qualquer writer
reversível. Ver [`M1K_A_EXCITER_PROTOCOL_EVIDENCE.md`](M1K_A_EXCITER_PROTOCOL_EVIDENCE.md).
Não liberar escrita com base apenas em esquemas documentados.

**Audio Lab futuro:** reprodução WAV, captura do retorno via USB,
A/B em volume ajustado, RMS, correlação L/R, espectro e exportações,
independentemente do processo HID de controle. O primeiro laboratório
poderá focar exclusivamente a cadeia Music, que já produz som USB.
