# Como Usar o Monitor de Dados JBL Quantum910

## Script Principal

**`/tmp/jbl_battery_hidraw.py`** - Versão completa com análise detalhada

## Execução Básica

```bash
sudo python3 /tmp/jbl_battery_hidraw.py
```

## Com Log em Arquivo

```bash
sudo python3 /tmp/jbl_battery_hidraw.py --log
```

O log será salvo em `/tmp/jbl_battery_log_YYYYMMDD_HHMMSS.txt`

## O que o Script Mostra

Para cada pacote recebido, o script exibe:

1. **Informações do Pacote**
   - Número do pacote
   - Timestamp
   - Tamanho em bytes

2. **Dados em Hexadecimal**
   - Formato simples (todos os bytes)
   - Formato agrupado (8 bytes por linha com offset)

3. **Dados em Decimal**
   - Todos os valores em formato decimal

4. **Tabela Detalhada**
   - Cada byte mostrado com:
     - Posição (índice)
     - Hexadecimal
     - Decimal
     - Binário (8 bits)
     - ASCII (se aplicável)

5. **Análise Detalhada**
   - Interpretação de cada byte individual
   - Análise de padrões multi-byte (16-bit, 32-bit)
   - Comparação com pacote anterior
   - Interpretações HID comuns
   - Candidatos a bateria
   - Sequências detectadas

6. **Detecção Automática de Bateria**
   - Identifica valores entre 0-100 que podem ser porcentagem
   - Destaque quando encontra possíveis valores de bateria

## Dicas de Análise

1. **Quando você apertar botões**, observe quais bytes mudam
2. **Compare pacotes diferentes** para identificar padrões
3. **Valores entre 0-100** são candidatos a bateria
4. **O primeiro byte** geralmente é o Report ID em dispositivos HID
5. **Sequências** podem indicar valores relacionados (ex: volume, bateria, etc.)

## Exemplo de Saída

```
============================================================
PACOTE #1 - 14:30:25.123
============================================================
Tamanho: 8 bytes

DADOS EM HEXADECIMAL:
  01 00 00 4f 00 00 00 00

HEXADECIMAL FORMATADO (8 bytes/linha):
  [00] 01 00 00 4f 00 00 00 00

DADOS EM DECIMAL:
    1   0   0  79   0   0   0   0

TABELA DETALHADA (Byte | Hex | Dec | Bin | ASCII):
  --------------------------------------------------------
  [ 0] 0x01 |   1 | 00000001 | '.'
  [ 1] 0x00 |   0 | 00000000 | '.'
  [ 2] 0x00 |   0 | 00000000 | '.'
  [ 3] 0x4f |  79 | 01001111 | 'O'
  ...

  NÍVEL DE BATERIA DETECTADO: 79% (byte 3)
```

## Análise Manual

Se a detecção automática não encontrar bateria, analise manualmente:

1. **Procure por valores que mudam lentamente** (bateria não muda a cada segundo)
2. **Compare pacotes quando você sabe que a bateria mudou** (ex: após carregar)
3. **Observe padrões** - bateria geralmente está em uma posição fixa
4. **Valores podem estar em escala diferente** (ex: 0-255 para 0-100%)

## Troubleshooting

- **Nenhum dado recebido**: Tente usar o fone (botões, volume, etc.)
- **Permissão negada**: Execute com `sudo`
- **Muitos dados duplicados**: Normal, o script ignora duplicatas consecutivas

