# Troubleshooting - Erros Comuns

## Erro: `[Errno 5] Input/output error`

### Causa
Este erro geralmente ocorre quando:
1. O dispositivo está sendo usado por outro programa
2. O dispositivo foi desconectado durante a leitura
3. O driver do kernel está controlando o dispositivo
4. Há conflito de acesso ao dispositivo

### Soluções

#### 1. Verificar se outro programa está usando o dispositivo

```bash
# Ver processos usando o dispositivo
lsof /dev/hidraw5
# ou
fuser /dev/hidraw5
```

Se houver processos, encerre-os:
```bash
sudo kill <PID>
```

#### 2. Verificar se o dispositivo está conectado

```bash
lsusb | grep JBL
ls -la /dev/hidraw5
```

Se não aparecer, o dispositivo foi desconectado.

#### 3. Desanexar driver do kernel (se usar pyusb)

```bash
# Verificar qual driver está usando
lsmod | grep usbhid

# Desanexar (pode ser necessário)
sudo modprobe -r usbhid
sudo modprobe usbhid
```

**Cuidado:** Isso pode afetar outros dispositivos USB HID.

#### 4. Reiniciar o dispositivo

1. Desconecte o fone USB
2. Aguarde 2 segundos
3. Reconecte o fone USB
4. Execute o script novamente

#### 5. Verificar permissões

```bash
ls -la /dev/hidraw5
# Deve mostrar: crw-rw-rw- ou crw-rw----

# Se não tiver permissão:
sudo chmod 666 /dev/hidraw5
```

#### 6. Usar script que não precisa de pyusb

Se o erro ocorrer com `jbl_battery_monitor.py` (pyusb), use:

```bash
sudo python3 jbl_battery_simple.py
# ou
sudo python3 jbl_battery_hidraw.py
```

Estes scripts usam hidraw diretamente e são mais estáveis.

## Erro: `Permission denied`

### Solução
```bash
sudo python3 jbl_battery_simple.py
```

Ou configure regras udev (veja `setup_udev_rules.sh).

## Erro: `ModuleNotFoundError: No module named 'usb'`

### Solução
```bash
# Para usuário normal
pip3 install pyusb --user

# Para root (se usar sudo)
sudo pip3 install pyusb
```

Ou use scripts que não precisam de pyusb:
```bash
sudo python3 jbl_battery_simple.py
```

## Dispositivo não envia dados

### Possíveis causas:
1. Dispositivo não está enviando periodicamente
2. Precisa pressionar botões para ativar
3. Dispositivo em modo de economia de energia

### Soluções:
1. **Aguarde** - O dispositivo envia a cada 7-11 segundos
2. **Pressione botões** do fone para ativar comunicação
3. **Use o fone** - Reproduza áudio, ajuste volume
4. **Reconecte** o dispositivo

## Script trava ou não responde

### Solução:
1. Pressione `Ctrl+C` para interromper
2. Verifique se o dispositivo está conectado
3. Reinicie o script

## Múltiplos erros de I/O

Se você receber muitos erros de I/O:

1. **Desconecte e reconecte** o fone
2. **Reinicie o script**
3. **Verifique** se há outros programas usando o dispositivo:
   ```bash
   ps aux | grep -i jbl
   ps aux | grep -i quantum
   ```

## Dicas Gerais

1. **Use `jbl_battery_simple.py`** - É o mais estável
2. **Execute com sudo** - Evita problemas de permissão
3. **Aguarde alguns segundos** - O dispositivo envia periodicamente
4. **Não use múltiplos scripts ao mesmo tempo** - Pode causar conflito

## Se Nada Funcionar

1. Desconecte o fone
2. Aguarde 5 segundos
3. Reconecte o fone
4. Aguarde 2 segundos
5. Execute:
   ```bash
   sudo python3 jbl_battery_simple.py
   ```

Se ainda não funcionar, verifique:
- Se o dispositivo aparece em `lsusb`
- Se o hidraw existe: `ls -la /dev/hidraw*`
- Se há erros no dmesg: `dmesg | tail -20`

