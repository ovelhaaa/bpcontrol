# BP1032: encapsulamento ACP em USB HID confirmado por captura

Data: 2026-11-22. Análise passiva do tráfego legítimo do ACPWorkbench.
Nenhum comando próprio foi enviado à placa; nenhum driver foi substituído.

## Resultado

Na captura válida, ACP trafega pela **interface 4 (MI_04)** usando transferências
**Control no endpoint 0**, com **SET_REPORT Output** seguido de **GET_REPORT Input**.
O campo Report ID das duas solicitações é **zero**, comprovado por `wValue`.
Cada carga de relatório contém **256 bytes**: ACP no offset 0 e zeros até o final.
Não foi observado uso de Interrupt, Bulk ou Feature Report nesta captura.

Isso descreve o comportamento capturado, não todas as capacidades do dispositivo.
O descritor HID não foi capturado; não se afirma que outros endpoints ou IDs inexistam.

## Preparação e proveniência

- Wireshark/TShark 4.6.10 e USBPcap instalados. Após reinicialização, driver ativo.
- Cadeia PnP: dispositivo composto → USB Root Hub (USB 3.0) →
  AMD USB 3.10 eXtensible Host Controller - 1.10 (Microsoft).
- Enumeração USBPcap no momento da captura: **USBPcap2, endereço 1**.
  A instância mudou entre reinicializações; o script agora a descobre a cada execução.
- Identidade anterior: VID/PID `1235:0003`, fabricante `MV-SILICON`, produto
  `mvsilicon B1 usb audio`, coleção MI_04, Usage Page `FF00`, Usage `55AA`.
  Esses dados vêm de enumeração Windows, não do PCAP sem descritores.
- Capacidades Windows informadas: Input 257, Output 257, Feature 9 bytes.
- `artifacts/usb-capture/` excluído via `.git/info/exclude`, sem inclusão no Git.
- Captura limitada a 30 segundos e filtrada na origem por endereço 1; sem `-A`,
  sem captura automática de novos dispositivos e sem injeção de descritores.
- A tentativa anterior, `chorus-01.pcapng`, tem zero pacotes e não é evidência ACP.

Fonte local válida: `artifacts/usb-capture/chorus-02.pcapng` (265252 bytes).
SHA256: `3dcbb841e63ecbdd3b4eaabe3f1475351ba3260d3849c6af74647a8772c5a7aa`.
São **1380 registros USBPcap**, abrangendo **29,038198 s** entre o primeiro e o último.
Todos pertencem ao bus 2/endereço 1. São 690 operações Control, cada uma com
submissão e conclusão, formando 345 ciclos de envio/recepção.
Todas as conclusões têm status zero; não há registros truncados.

O USBPcap registra URBs, não transações físicas no fio. Esses números não medem
quantos pacotes USB DATA foram transmitidos pelo controlador.

## Solicitações USB confirmadas

| Campo | Envio ACP | Recepção ACP |
|---|---|---|
| bmRequestType | `21` (Host→Device, Class, Interface) | `A1` (Device→Host, Class, Interface) |
| bRequest | `09` SET_REPORT | `01` GET_REPORT |
| wValue | `0200`: Output, ID 0 | `0100`: Input, ID 0 |
| wIndex | `0004` | `0004` |
| wLength | 256 | 256 |
| Endpoint no USBPcap | `00` | `80` |
| Endpoint físico lógico | EP0 OUT | EP0 IN |

`0x80` aqui indica a direção IN do endpoint **zero**, não um endpoint Interrupt 0x80.
O `wIndex=4` em todas as 690 solicitações isola MI_04; MI_03 não aparece.
O significado dos campos segue HID 1.11, seções 7.2.1/7.2.2:
[especificação USB-IF](https://www.usb.org/sites/default/files/hid1_11.pdf).

O primeiro byte da carga USB é `A5`, não `00`. O ID zero é indicado no setup,
sem prefixo adicional nesta carga capturada. O Usage `0x55AA` não é cabeçalho ACP.

## Tamanhos, offsets e preenchimento

| Registro por ciclo | Quantidade | Cabeçalho USBPcap | Dados registrados | Total capturado |
|---|---:|---:|---:|---:|
| SET_REPORT Setup + saída | 345 | 28 | 8 setup + 256 relatório | 292 |
| SET_REPORT Complete | 345 | 28 | 0 | 28 |
| GET_REPORT Setup | 345 | 28 | 8 setup | 36 |
| GET_REPORT Complete + entrada | 345 | 28 | 256 relatório | 284 |

Todos os 690 relatórios com carga contêm exatamente um quadro ACP completo,
validado por assinatura `A5 5A`, LEN e terminador `16`, no offset **0 do relatório**.
Todos os bytes após o quadro ACP são zero. Nenhuma fragmentação ACP entre URBs
foi necessária ou observada. Isso não revela `wMaxPacketSize`, que não está no PCAP.

Na saída, ACP está no offset 36 do registro USBPcap (28 cabeçalho + 8 setup);
na entrada, no offset 28. Esses offsets não são cabeçalhos do protocolo embarcado.
O layout do capturador está documentado no
[código oficial USBPcap](https://github.com/desowin/usbpcap/blob/master/USBPcapDriver/include/USBPcap.h).

## Guitar Chorus: duas trocas completas

| Troca | Quadros originais | Quadros sanitizados | Tempo relativo da consulta | Consulta→resposta |
|---|---|---|---:|---:|
| 1 | 397–400 | 1–4 | 3,970989 s | 5,268 ms |
| 2 | 1009–1012 | 5–8 | 12,841705 s | 4,885 ms |

Cada troca apresenta: SET_REPORT com consulta; conclusão USB sem carga;
GET_REPORT; conclusão contendo a resposta. A conclusão USB vazia não é um ACK ACP.
Os pares submissão/conclusão são vinculados pelo IRP dentro da sua vida útil.
O mesmo endereço IRP é reutilizado em operações sucessivas: não deve ser usado
como identificador global de sessão ou como vínculo entre o SET e o GET.

Consulta em ambas:

```text
A5 5A 8F 00 16
```

São 5 bytes ACP + **251 zeros** até completar 256.
Resposta em ambas:

```text
A5 5A 8F 0F FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00 16
```

São 20 bytes ACP + **236 zeros**. LEN `0F` cobre `FF` e sete valores de 16 bits.
Valores decodificados little-endian: **[1, 20, 10, 200, 50, 80, 80]**.
Aplicando o esquema já existente no repositório: enable=1, delay=20 ms,
depth=10 ms, rate=2 Hz, feedback=50%, dry=80%, wet=80%.
Os números e bytes são evidência PCAP; os nomes/unidades dependem do esquema
prévio e não são demonstrados por esta captura isoladamente.

A associação consulta/resposta é fortemente sustentada pela sequência consecutiva,
comando `8F`, formato esperado e repetição idêntica. Não há número de sequência ACP
observado que prove causalidade independentemente da ordem temporal.

Também existem 29 consultas de firmware (`A5 5A 00 00 16`) e 27 de status
(`A5 5A 02 00 16`), com respostas completas de mesmo comando. Não houve comandos
ACP `FD` ou `FE`. Outros comandos foram observados, incluindo `80` com um byte de
payload; payload não vazio, por si só, não prova escrita. Sua semântica não foi
investigada e esses pacotes não estão no arquivo sanitizado.

O operador relatou alterações de parâmetros na primeira tentativa vazia; elas
não foram registradas. Não é possível atribuir os valores atuais a essas ações,
nem inferir persistência em flash a partir desta captura.

## Arquivo filtrado e sanitização

`artifacts/usb-capture/chorus-sanitized.pcap`: **8 registros**, somente as duas
trocas de leitura `8F` completas. SHA256:
`54dc3b39defd13e955bb09358276dc6f05502e0172be7cfff3372601bbdf2c68`.

O arquivo é reconstruído em PCAP clássico com cargas dos relatórios preservadas.
Foram removidos todos os outros intercâmbios, metadados PCAPNG do host,
timestamps absolutos e endereços IRP do kernel. Bus e endereço USB normalizados
para 1/1, IRPs substituídos por tokens sequenciais e época sintética iniciada
em 1 segundo Unix. Intervalos relativos entre as trocas foram preservados.
Não contém descritores, strings USB, números de série, caminhos ou outros dispositivos.
É um derivado sanitizado, não uma cópia binária forense do original.

O arquivo bruto e o JSON completo permanecem apenas locais; o JSON pode conter
cargas de outros comandos da mesma placa e não deve ser tratado como sanitizado.
Nada foi publicado, commitado ou enviado por push.

## Reprodução offline

Executar na raiz do projeto (usar nome novo para o PCAP de saída):

```powershell
python tools/analyze_usb_capture.py artifacts/usb-capture/chorus-02.pcapng --bus 2 --device 1 --output artifacts/usb-capture/reanalysis.json --sanitized-pcap artifacts/usb-capture/chorus-sanitized-new.pcap
```

O script usa TShark para converter PCAPNG e interpreta LINKTYPE_USBPCAP em Python.
Expõe setup, estágio, direção, tamanhos, status, truncamento, IDs de transação
locais, candidatos ACP, prefixo/sufixo e hipóteses temporais. A exportação sanitizada
recusa sequências diferentes do padrão de leitura Chorus validado, respostas
incompletas e caudas não nulas. Não implementa remontagem especulativa entre URBs.
Não abre dispositivos nem transmite USB.

## Proposta concreta para a primeira consulta BPControl

Implementar futuramente `WindowsHidControlTransport.read_guitar_chorus()`, com uma
única consulta permitida, usando **HidD_SetOutputReport + HidD_GetInputReport**.
Essas APIs correspondem às operações de relatório observadas; não iniciar por
`hid.write()/ReadFile`, cujo caminho Interrupt não foi observado, nem usar Feature.
O PCAP não revela qual API específica o ACPWorkbench chamou.

1. Exigir ACPWorkbench fechado. Enumerar somente MI_04, VID/PID, strings,
   Usage Page/Usage e capacidades esperadas; rejeitar ambiguidade.
2. Abrir a coleção com compartilhamento apropriado, verificando cada erro Windows.
3. Montar **buffer Windows de 257 bytes**: `00` de seletor do ID, seguido de
   `A5 5A 8F 00 16` e 251 zeros. Chamar `HidD_SetOutputReport` com comprimento 257.
4. Preparar buffer de entrada de 257 bytes zerado, ID 0, e chamar
   `HidD_GetInputReport`. Validar resultado e remover apenas o seletor da API.
5. Validar os 256 bytes restantes: ACP no offset 0, comando `8F`, LEN=15,
   marcador `FF`, terminador `16`, sete valores e cauda nula. Reutilizar
   `decode_frame`/`decode_readback` existentes; rejeitar resposta inesperada.
6. Uma consulta, sem polling contínuo ou repetição automática. Isolar as APIs
   síncronas em processo auxiliar com prazo de 2 s; um timeout encerra o auxiliar,
   libera seus handles e retorna erro sem retransmitir. Fechar handles em `finally`.
7. Validar primeiro o empacotamento offline com o PCAP sanitizado. Para ensaio ativo
   futuro, capturar em paralelo e comparar os setups e as cargas com esta evidência.

O byte adicional da API Windows é uma convenção documentada, coerente com as
capacidades 257 e as cargas USB de 256; não foi visto no barramento:
[SetOutputReport](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_setoutputreport),
[GET_INPUT_REPORT](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidclass/ni-hidclass-ioctl_hid_get_input_report).
Não há implementação de transporte ativo nesta entrega. A primeira execução
ativa permanece uma etapa futura distinta da investigação passiva solicitada.

## Validação

- TShark confirmou os setups e a correspondência das conclusões no derivado.
- O derivado tem 8 registros, sem indicação `_ws.malformed`.
- Testes offline cobrem IRP reutilizado, preservação das cargas na sanitização,
  rejeição de cauda não nula, sobrescrita, truncamento, LEN/terminador e offsets.
- Os 17 testes do projeto passaram (4 novos). Com o pacote ainda não instalado
  no Python global, a execução usou `sys.path.insert(0, 'src')` antes de descobrir
  os testes; não foi necessário instalar dependências nem modificar o ambiente.
- Nenhum processo USBPcapCMD, TShark ou dumpcap permaneceu ativo ao finalizar.
