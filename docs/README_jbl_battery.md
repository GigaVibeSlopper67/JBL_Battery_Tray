# Monitor de Bateria JBL Quantum910 Wireless

Scripts para interceptar a comunicação USB do fone JBL Quantum910 e extrair informações de bateria.

## Scripts Disponíveis

### 1. `jbl_battery_monitor.py` (usando pyusb)
Script principal que usa a biblioteca `pyusb` para comunicação direta com o dispositivo USB.

### 2. `jbl_battery_hidapi.py` (usando hidapi)
Script alternativo usando `hidapi`, que pode ser mais fácil de usar em alguns sistemas.

## Requisitos

```bash
pip3 install pyusb --user
# ou
pip3 install hidapi --user
```

## Permissões

Para acessar dispositivos USB, você pode precisar de permissões especiais:

### Opção 1: Executar como root (não recomendado)
```bash
sudo python3 /tmp/jbl_battery_monitor.py
```

### Opção 2: Configurar udev rules (recomendado)
Crie o arquivo `/etc/udev/rules.d/99-jbl-quantum910.rules`:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2088", MODE="0666"
```

Depois recarregue as regras:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Opção 3: Adicionar usuário ao grupo plugdev
```bash
sudo usermod -a -G plugdev $USER
# Faça logout e login novamente
```

## Como Usar

1. Conecte o fone JBL Quantum910 via USB
2. Execute um dos scripts:
   ```bash
   python3 /tmp/jbl_battery_monitor.py
   # ou
   python3 /tmp/jbl_battery_hidapi.py
   ```
3. O script irá:
   - Mostrar informações do dispositivo
   - Monitorar continuamente a comunicação USB
   - Tentar identificar o nível de bateria nos dados recebidos
   - Exibir dados brutos em hexadecimal e decimal

## Interpretação dos Dados

O script tenta várias interpretações dos dados recebidos:
- Procura por valores entre 0-100 que podem representar porcentagem
- Interpreta dados como 8-bit ou 16-bit
- Procura padrões comuns de relatórios HID

## Notas

- O nível de bateria pode não ser enviado continuamente pelo dispositivo
- Pode ser necessário usar o fone ativamente para que ele envie dados
- O formato exato dos dados depende da implementação do fabricante
- Alguns dispositivos só enviam informações de bateria quando solicitadas

## Troubleshooting

Se o script não encontrar o dispositivo:
- Verifique se o fone está conectado: `lsusb | grep JBL`
- Verifique permissões: `ls -la /dev/bus/usb/001/007`
- Tente executar como root para testar

Se não receber dados:
- O dispositivo pode não estar enviando dados continuamente
- Tente usar o fone (reproduzir áudio, ajustar volume) para ativar comunicação
- Alguns dispositivos requerem comandos específicos para reportar bateria

