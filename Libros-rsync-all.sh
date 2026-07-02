#!/bin/bash

# Directorio base local
BASE_DIR="$HOME/Personal"
TMP_BIN="/tmp/bin"
# Servidor de destino
REMOTE_SERVER="demo"

# Limpiar y preparar el directorio temporal local
echo "Preparando directorio temporal en $TMP_BIN..."
rm -rf "$TMP_BIN"
mkdir -p "$TMP_BIN"

# Asegurar que estamos en el directorio base
cd "$BASE_DIR" || exit 1

# Recorrer cada directorio que coincida con Processed_htm_audios-*
for dir in Processed_htm_audios-*; do
    # Verificar si es un directorio y no está vacío o es un patrón literal
    [ -d "$dir" ] || continue
    
    # Extraer el nombre de la categoría
    # De: Processed_htm_audios-<nombre-de-la-categoria>
    categoria="${dir#Processed_htm_audios-}"
    
    # Si la categoría queda vacía, saltar
    [ -n "$categoria" ] || continue
    
    echo "Preparando categoría localmente: $categoria (desde $dir)"
    
    # Crear la carpeta de la categoría en /tmp/bin
    mkdir -p "$TMP_BIN/$categoria"
    
    # Recorrer todos los archivos .htm dentro de este directorio
    for file in "$dir"/*.htm; do
        # Verificar que existan archivos .htm
        [ -f "$file" ] || continue
        
        # Obtener el nombre del archivo sin la ruta
        filename=$(basename "$file")
        # Cambiar la extensión .htm por .html
        new_filename="${filename%.htm}.html"
        
        # Copiar al directorio temporal con el nuevo nombre, preservando marcas de tiempo (timestamp)
        # Esto permite que rsync detecte correctamente si el archivo ya existe y no ha cambiado.
        cp -p "$file" "$TMP_BIN/$categoria/$new_filename"
    done
done

echo "Subiendo archivos al servidor remoto demo:~/bin/ usando rsync..."
# Sincronizar la estructura de /tmp/bin/ al servidor destino usando rsync -avz --delete
# Usamos -a (archivo: conserva permisos, marcas de tiempo, etc.), -v (detallado), -z (compresión)
# La opción --delete elimina los archivos en el destino que ya no existen en el origen (locales)
# La barra diagonal al final de "$TMP_BIN/" asegura que se sincronice el contenido y no el directorio 'bin' en sí
rsync -avz --delete "$TMP_BIN/" "$REMOTE_SERVER:~/bin/"

# Limpiar el directorio temporal local
echo "Limpiando directorio temporal..."
rm -rf "$TMP_BIN"

echo "¡Proceso de sincronización finalizado con éxito!"
