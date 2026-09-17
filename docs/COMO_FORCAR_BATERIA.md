# Como Forçar o Envio de Informações de Bateria

## Problema

O JBL Quantum910 só envia informações de bateria quando:
- O cabo USB é conectado/desconectado
- Botões são pressionados
- Em intervalos específicos (não contínuo)

## Soluções

### 1. Script de Captura Durante Conexão

Use `jbl_battery_capture.py` para:
- Capturar tudo que acontece durante conexão
- Analisar os pacotes recebidos
- Tentar forçar com feature reports

```bash
sudo python3 jbl_battery_capture.py
```

**Como usar:**
1. Execute o script
2. Desconecte o fone USB
3. Conecte o fone USB novamente
4. O script vai capturar e analisar tudo

### 2. Script de Força Bruta

Use `jbl_battery_force.py` para:
- Tentar vários comandos diferentes
- Usar feature reports HID
- Forçar o dispositivo a responder

```bash
sudo python3 jbl_battery_force.py
```

### 3. Monitoramento Contínuo com Botões

O script `jbl_battery_simple.py` funciona quando você:
- Pressiona botões do fone
- Ajusta volume
- Usa controles do fone

```bash
sudo python3 jbl_battery_simple.py
```

## Análise dos Dados

### Padrão Identificado

Quando o dispositivo envia bateria:
```
08 1e = [8, 30] = 30% de bateria
```

- **Byte 0**: Report ID = `0x08` (fixo)
- **Byte 1**: Nível de bateria = `0x1e` (30) = **30%**

### O que Tentar

1. **Feature Reports HID**
   - Report ID 0x08 (o que recebemos)
   - Outros Report IDs comuns (0x01-0x09)

2. **Comandos de Solicitação**
   - Alguns dispositivos respondem a feature reports GET
   - Pode precisar enviar um comando específico

3. **Timing**
   - O dispositivo pode enviar bateria apenas em momentos específicos
   - Durante inicialização é o mais confiável

## Limitações

- O dispositivo pode não responder a comandos externos
- Pode ser necessário usar botões físicos
- Alguns dispositivos só enviam quando há mudança de estado

## Próximos Passos

1. Execute `jbl_battery_capture.py` e analise os pacotes
2. Tente identificar se há algum padrão nos comandos
3. Use os botões do fone para ativar o envio quando necessário

