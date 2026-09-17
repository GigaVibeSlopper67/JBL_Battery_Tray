# Requisitos e Instalação

## Bibliotecas Python Necessárias

### Para `jbl_battery_monitor.py` (pyusb)
```bash
# Instalar para usuário normal
pip3 install pyusb --user

# Instalar para root (necessário se usar sudo)
sudo pip3 install pyusb
```

### Para `jbl_battery_hidapi.py` (hidapi)
```bash
# Instalar para usuário normal
pip3 install hidapi --user

# Instalar para root (necessário se usar sudo)
sudo pip3 install hidapi
```

### Para `jbl_battery_hidraw.py` e `jbl_battery_simple.py`
**Não precisa de bibliotecas externas!** Usa apenas bibliotecas padrão do Python.

## Verificação

### Verificar se pyusb está instalado
```bash
python3 -c "import usb.core; print('OK')"
sudo python3 -c "import usb.core; print('OK')"  # Para root
```

### Verificar se hidapi está instalado
```bash
python3 -c "import hid; print('OK')"
sudo python3 -c "import hid; print('OK')"  # Para root
```

## Recomendação

**Use os scripts que não precisam de bibliotecas externas:**
- `jbl_battery_simple.py` (recomendado)
- `jbl_battery_hidraw.py` (análise completa)

Estes scripts usam apenas bibliotecas padrão do Python e funcionam com `sudo` sem instalar nada adicional.

## Solução Rápida

Se você receber erro de módulo não encontrado ao usar `sudo`:

```bash
# Opção 1: Instalar para root
sudo pip3 install pyusb

# Opção 2: Usar script que não precisa de bibliotecas
sudo python3 jbl_battery_simple.py
# ou
sudo python3 jbl_battery_hidraw.py
```

