# Padrão de Bateria Identificado - JBL Quantum910

## Padrão Confirmado

**Formato do pacote de bateria:**
```
[Report ID, Nível de Bateria]
```

**Exemplo identificado:**
```
08 1e = [8, 30] = 30% de bateria
```

## Estrutura dos Dados

- **Byte 0**: Report ID = `0x08` (8 em decimal)
- **Byte 1**: Nível de bateria = `0x1e` (30 em decimal) = **30%**

## Análise

- O **Report ID** (`0x08`) parece ser fixo para pacotes de bateria
- O **nível de bateria** está no byte 1, em formato decimal direto (0-100)
- O pacote tem 2 bytes mínimos, mas pode ter mais bytes (provavelmente zeros ou outros dados)

## Scripts

### Script Simplificado
Use `jbl_battery_simple.py` para monitorar apenas a bateria:

```bash
sudo python3 jbl_battery_simple.py
```

Este script:
- Foca apenas no byte 1 quando o Report ID é 0x08
- Mostra barra visual de bateria
- Exibe status (Carregada/Boa/Média/Baixa)
- Ignora outros pacotes

### Script Completo
Use `jbl_battery_hidraw.py` para análise completa de todos os dados:

```bash
sudo python3 jbl_battery_hidraw.py
```

## Testes Recomendados

1. **Teste com diferentes níveis de bateria:**
   - Carregue o fone e observe se o valor aumenta
   - Use o fone e observe se o valor diminui
   - Compare com indicador do sistema (se disponível)

2. **Verifique outros pacotes:**
   - Pressione diferentes botões
   - Ajuste volume
   - Observe se o Report ID muda para outros valores

3. **Confirme o padrão:**
   - O Report ID sempre é 0x08 para bateria?
   - O byte 1 sempre está entre 0-100?
   - Há outros bytes relevantes no pacote?

## Notas

- O dispositivo pode não enviar dados continuamente
- Pode ser necessário pressionar botões para ativar o envio
- O formato pode variar em diferentes modelos/firmwares

## Data de Identificação

25 de Janeiro de 2025

