#!/bin/bash
# Recorrer todos los directorios que coincidan con el patrón
for folder in "$HOME"/Personal/Libros-*; do
    # Verificar que realmente sea un directorio
    if [ -d "$folder" ]; then
        echo "Procesando: $folder"
        # Entrar al directorio
        cd "$folder" || continue
        # Ejecutar el comando
        echo -e "2\n2\n3\nsi\n0" | bash init.sh
        # Opcional: regresar al directorio anterior (buena práctica)
        cd - > /dev/null
    fi
done