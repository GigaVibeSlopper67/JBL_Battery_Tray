# Instruções para Monitorar Bateria do JBL Quantum910

## Status Atual

Dispositivo detectado: JBL Quantum910 (Bus 001 Device 007)  
Interface HID identificada: `/dev/hidraw5`  
Permissões necessárias: Requer acesso root ou configuração udev

## Scripts Disponíveis

1. **`jbl_battery_hidraw.py`** **RECOMENDADO**
   - Lê diretamente do dispositivo hidraw
   - Mais eficiente e direto
   - Arquivo: `/tmp/jbl_battery_hidraw.py`

2. **`jbl_battery_monitor.py`**
   - Usa pyusb para comunicação USB direta
   - Arquivo: `/tmp/jbl_battery_monitor.py`

3. **`jbl_battery_hidapi.py`**
   - Versão alternativa usando hidapi
   - Arquivo: `/tmp/jbl_battery_hidapi.py`

## Como Usar (Opção 1: Com Sudo)

Execute diretamente com permissões de root:

```bash
sudo python3 /tmp/jbl_battery_hidraw.py
```

## Como Usar (Opção 2: Configurar Permissões Permanentes)

### Passo 1: Configurar regras udev

```bash
sudo /tmp/setup_udev_rules.sh
```

Ou manualmente:

```bash
sudo nano /etc/udev/rules.d/99-jbl-quantum910.rules
```

Adicione:
```
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="0ecb", ATTRS{idProduct}=="2088", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2088", MODE="0666", GROUP="plugdev"
```

### Passo 2: Recarregar regras e reconectar

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
# Desconecte e reconecte o fone
```

### Passo 3: Adicionar usuário ao grupo plugdev (se necessário)

```bash
sudo usermod -a -G plugdev $USER
# Faça logout e login novamente
```

### Passo 4: Executar o script

```bash
python3 /tmp/jbl_battery_hidraw.py
```

## Como Funciona

O script:
1. Abre o dispositivo `/dev/hidraw5` (correspondente ao JBL Quantum910)
2. Lê dados em tempo real da comunicação HID
3. Analisa os dados recebidos procurando por valores que representam bateria
4. Exibe dados brutos em hexadecimal e decimal
5. Tenta identificar automaticamente o nível de bateria

## Interpretação dos Dados

O script tenta várias interpretações:
- **Método 1**: Procura valores entre 0-100 que podem ser porcentagem
- **Método 2**: Interpreta como valores 16-bit (little-endian)
- **Método 3**: Procura padrões comuns de relatórios HID

## Dicas

- O dispositivo pode não enviar dados continuamente
- Tente usar o fone ativamente (reproduzir áudio, ajustar volume) para ativar comunicação
- Os dados brutos são sempre exibidos para análise manual
- O formato exato depende da implementação do fabricante

## Troubleshooting

### "Permissão negada"
- Execute com `sudo` ou configure regras udev

### "Dispositivo não encontrado"
- Verifique se o fone está conectado: `lsusb | grep JBL`
- Verifique qual hidraw corresponde: `ls -la /sys/bus/hid/devices/0003:0ECB:2088.0006/hidraw`

### "Nenhum dado recebido"
- O dispositivo pode não estar enviando dados automaticamente
- Tente usar o fone (reproduzir áudio, ajustar botões)
- Alguns dispositivos requerem comandos específicos para reportar bateria

### Mudança de hidraw
Se o número do hidraw mudar (não for mais hidraw5), edite o script e altere:
```python
HIDRAW_DEVICE = "/dev/hidraw5"  # Altere para o número correto
```

Para descobrir qual hidraw corresponde ao dispositivo:
```bash
ls -la /sys/bus/hid/devices/0003:0ECB:2088.0006/hidraw
```

