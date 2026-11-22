# M1I — triangulação do protocolo V2.40.0, SDK BP1048 e adaptação ESP32

Data da revisão: 2026-11-22. **Pesquisa documental e inspeção de código somente; nenhuma conexão USB, alteração de parâmetros ou gravação em flash foi executada nesta revisão.**

## Fontes primárias comparadas

1. **\`固件与用户应用程序通信协议V2.40.0.pdf\`**, MVSilicon, edição 2024-06-11, 78 páginas. PDF fornecido pelo operador; não duplicado no repositório.
2. **\`ACPWorkbench-ENG.pdf\`**, §6.1.27 (Chorus) e §6.1.30 (Ping Pong), e **\`ACPWorkbench.ini\`** fornecidos previamente.
3. **[SDK BP1048 v0.1.12](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12)**:
   - [\`chorus.h\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/MVsB1_Base_SDK/middleware/audio/inc/chorus.h) (algoritmo Chorus 1.1.1);
   - [\`pingpong.h\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/MVsB1_Base_SDK/middleware/audio/inc/pingpong.h) (algoritmo PingPong 1.4.1);
   - [\`audio_effect_library.h\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/MVsB1_Base_SDK/middleware/audio/inc/audio_effect_library.h) (\`AUDIO_EFFECT_LIBRARY_VERSION "1.35.1"\`);
   - [\`communication.c\`, \`Communication_Effect_Chorus\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/BT_Audio_APP/bt_audio_app_src/audio/communication.c#L4350-L4502);
   - [\`audio_effect.c\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/BT_Audio_APP/bt_audio_app_src/audio/audio_effect.c);
   - [\`ctrlvars.c\`](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12/blob/main/BT_Audio_APP/bt_audio_app_src/audio/ctrlvars.c#L461-L477).
4. **[ESP32 DSP Core / release](https://github.com/Ohminecraft/esp32-dsp-core/tree/release)**: reimplementações C++ em \`src/effects\`, com [Virtual Bass em \`unused/\`](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/unused/effects/virtual_bass.cpp).
5. **Capturas BP1032** da M1F e M1H: firmware 0x30, versão 0.3.0, \`effects_library_version=2.24.0\`, Chorus físico \`[1,20,10,200,50,80,80]\`, wet \`80→81→80\` validado por ACK/readback.

Não interpretar os números **documento/protocolo 2.40.0**, **biblioteca da BP1032 2.24.0**, **biblioteca do pacote SDK BP1048 1.35.1** ou **algoritmo Chorus 1.1.1** como uma sequência de versões da mesma entidade. São camadas e sistemas de versão diferentes. A similaridade de protocolo e cabeçalhos **não garante** equivalência binária nem semântica entre as duas placas/firmwares.

## 1. ACP é a interface de controle; não a API DSP interna

No protocolo V2.40.0, §§2.3, 3 e 5.20:

- Transporte USB usa HID; o quadro ACP é \`A5 5A CMD LEN DATA 16\` e os valores de 16 bits usam little-endian.
- \`0x80\` lista instâncias e tipos. A lista devolvida pelo firmware determina qual efeito ocupa cada \`0x81..0xFB\`; o tipo não é necessariamente igual ao índice.
- Ler um efeito: \`CMD\` com \`LEN=0\`. Resposta: \`FF\` + os parâmetros consecutivos de 16 bits.
- Escrever um campo: \`CMD\`, índice do parâmetro e valor de 16 bits. O **índice interno 255** permite enviar todos os parâmetros do efeito, mas é operação distinta do **comando \`0xFF\`** de chave/senha.
- Resposta a escrita: um byte de comando (ACK), **não** prova isoladamente que o firmware armazenou o valor pretendido; validar os sete campos por nova leitura.

Esta é a camada que o BPControl já usa com êxito no HID MI_04. A API \`chorus_init/chorus_apply\` da biblioteca BP1048 é chamada **dentro do firmware**, não através do ACP diretamente.

## 2. Chorus: evidência sobre a escala LFO

| Fonte | Fato observado/documentado |
|---|---|
| Protocolo chinês V2.40 §5.20.27, PDF p.57 | Campo 3 modulation_rate: raw 0–100, padrão 10; a tabela **não explicita Hz por unidade** |
| Manual inglês ACPWorkbench §6.1.27, PDF p.27 | Raw 2=0,2 Hz, 10=1,0 Hz, 100=10,0 Hz; equivale a raw/10 |
| SDK BP1048 \`chorus.h\` 1.1.1 | \`chorus_init\` e \`chorus_apply\` documentam igualmente **0,1 Hz por unidade** e 0–10 Hz |
| Exemplo de firmware BP1048 \`communication.c\` | No **case 3**, uma tentativa de escrita \`mod_rate>100\` é substituída por **10**; resposta de leitura contém o valor salvo em \`p->mod_rate\` |
| Exemplo \`audio_effect.c\` | Passa \`unit->mod_rate\` diretamente às funções \`chorus_init\` e \`chorus_apply\`; não há fator ×10 ou ÷10 nesse caminho do exemplo |
| \`ACPWorkbench.ini\` | Valor de configuração \`modulation_rate=10\`; **não** comprova o estado da BP1032 |
| Log ACPWorkbench antigo | Mostra uma escrita de **raw 100** com ACK/readback; não contém o texto em Hz exibido pela interface nessa operação |
| Placa BP1032, M1F | Leitura física **raw 200**, superior ao máximo indicado pelo protocolo/SDK de exemplo |

**Conclusão ajustada:** \`raw/10\` tem **concordância documental e de API dentro do SDK BP1048**. A hipótese antiga \`raw/100\` do BPControl **não possui o mesmo nível de sustentação para Chorus**; é possível que tenha sido confundida com outros efeitos, como o Flanger (§5.20.34), no qual 0–1000 equivale a 0–10Hz. **A escala e a faixa efetivas da BP1032 continuam não comprovadas**: o raw 200 pode refletir outra implementação, perfil, preset, inicialização ou ausência da mesma validação no firmware instalado. Não atribuir automaticamente 2 Hz nem 20 Hz a esse valor.

**Decisão:** campo 3 continua **somente leitura** e aparece como escala pendente; os valores raw são exibidos sem conversão em Hz. A origem de todos os limites fica visível na GUI M1I.

## 3. Ping Pong: milissegundos na ACP, amostras na API interna

Esta aparente contradição tem uma **resolução arquitetural concreta**:

| Camada | Unidade |
|---|---|
| Protocolo V2.40 §5.20.30, campo 2 \`delay\`, padrão \`250ms\`; campo 5 \`max_delay\`, padrão \`1000ms\` | **milissegundos** |
| Manual inglês ACPWorkbench §6.1.30 | Descreve o argumento do algoritmo em **amostras** |
| SDK BP1048 \`pingpong.h\`: \`pingpong_apply(...delay_samples...)\`; \`pingpong_init(...max_delay_samples...)\` | **amostras PCM** |
| Firmware de exemplo \`ctrlvars.c\` linhas 469–477 | \`delay_samples = delay_ms × sample_rate / 1000\`, e mesma fórmula para \`max_delay\` |

**Conclusão:** o BPControl deve conservar **ms** para o valor de controle ACP do Ping Pong, e **samples** para a API interna do algoritmo. A conversão acontece na aplicação de firmware. A versão **exata** da firmware BP1032 e os limites específicos continuam requerendo prova de readback, sobretudo quando o \`max_delay\` influencia memória e troca de modo de qualidade.

A implementação \`pingpong.h\` usa amostras estéreo e reservas de buffer dependentes de \`high_quality\`. Isto ajuda a entender o crescimento de RAM capturado fisicamente, mas **não prova** que a BP1032 possui a mesma implementação de codificação ou alocação.

## 4. O que o ESP32 DSP Core realmente acrescenta

A branch \`release\` de \`Ohminecraft/esp32-dsp-core\` traz códigos C++ próprios para **Exciter, DRC multibanda, Compander, EQ, Dynamic Bass, Dynamic EQ, ISF, Volume** e outros; [\`unused/effects/virtual_bass.cpp\`](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/unused/effects/virtual_bass.cpp) declara expressamente ser uma *reimplementação baseada na arquitetura* da biblioteca BP1048.

O projeto usa \`DspModule\`, processamento PCM, gerenciamento de estados e interfaces UART/WebSocket. **Não é uma porta do protocolo USB HID/ACP da BP1032** e **não contém Chorus nem Ping Pong ativos** no diretório \`src/effects\` inspecionado. Seu valor para o BPControl é oferecer ideias para uma plataforma DSP/visualização separada, compatibilidade conceitual de parâmetros, testes em PC/WASM e um futuro frontend — **não** comprovar o comportamento musical do firmware proprietário BP1032.

O SDK contém **headers C e arquivos \`.a\` de biblioteca binária**. Os headers informam assinaturas, faixas e layout de estados; o \`libAudioEffectLibrary.a\` não fornece código C portátil para ESP32/WASM e foi compilado para a arquitetura do SDK. A adaptação ESP32 é código novo, não a execução binária da biblioteca original.

## 5. Consequências para o projeto BPControl

1. **Camada \`protocol\`**: comandos, slots, índice, payload little-endian; consolidar o modelo já testado, sem abrir allowlist geral.
2. **Camada \`parameter_schema\`**: metadados derivados do V2.40, manual e headers; diferenciações por origem, versão e confiança. Para Chorus campo3, marcar *documentação concordante para API BP1048 / escala BP1032 não comprovada*.
3. **Camada \`hardware_evidence\`**: firmware reportado, baseline, ACK/readback físico, divergências; fonte de autoridade para habilitar cada escrita.
4. **Camada \`editor\`**: mostrar valores brutos atuais e parâmetros somente leitura, ao lado de limites/documentação e candidatos de conversão claramente rotulados. Só wet \`0x8F:6\` continua habilitado.
5. **Camada \`dsp_emulation\`**: manter separada do host BP1032, pois recriar sonoridade no PC ou ESP32 não prova equivalência ao binário da placa.

### Próximo ensaio, somente leitura

Com BPControl **fechado**, abrir ACPWorkbench e observar o valor exibido de *Modulation Rate* do Chorus sem editar nada; registrar versão do software e screenshot. Fechar ACPWorkbench; abrir BPControl em modo autorizado apenas para **Consultar Chorus (USB)**, e comparar o \`raw\` do campo3. Se o estado mudar entre as duas leituras, não formar um par. Nenhuma escrita adicional é necessária para esta etapa.

**Não fazer:** escrever raw 200 no firmware de exemplo; mandar campo255/all parameters; habilitar parâmetros pelos defaults do manual; salvar \`0xFD\`; atualizar \`0xFE\`; presumir que a placa BP1032 implementa as verificações do exemplo BP1048.

## Resultados e limitações

- A consulta dos três repositórios e do protocolo foi feita **offline/no GitHub**, sem acesso à placa.
- As notas de \`chorus.h\` são evidência da API documentada, e o código \`communication.c\` é evidência da *aplicação de exemplo BP1048*, não do código-fonte da firmware física BP1032.
- As diferenças de unidade no PingPong estão explicadas por uma ponte ms→samples documentada no código-fonte do SDK.
- O único ensaio de escrita BPControl aprovado na placa permanece Chorus **wet ±1** com ACK, readback e Undo.
