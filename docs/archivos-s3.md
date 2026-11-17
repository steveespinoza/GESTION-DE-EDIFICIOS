# Archivos privados en S3

El SuperAdmin puede adjuntar varios documentos y un comprobante de pago al proveedor desde la ficha de una factura. La API recibe PDF, PNG y JPEG de hasta 10 MiB por archivo y comprueba que la extensión coincida con la firma del archivo. PostgreSQL guarda los metadatos. S3 guarda el contenido bajo el prefijo `invoice-files/`.

Los comprobantes de pago que envía un propietario se guardan bajo `payment-proofs/` y admiten los mismos tipos y tamaño. Para descargarlos, el SuperAdmin debe abrir el reporte del edificio correspondiente. El propietario puede descargar los comprobantes que envió para sus unidades.

La API verifica la sesión y el alcance del archivo antes de generar una URL de cinco minutos. Mientras esté vigente, quien tenga el enlace puede usarlo. El navegador descarga el archivo como adjunto. [URLs firmadas de S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)

## Configurar el bucket

1. En la consola de Amazon S3, crea o selecciona un bucket privado, anota su nombre y región, y mantén habilitado **Bloquear todo acceso público**. Puedes conservar las ACL deshabilitadas con **Bucket owner enforced**. [Bloquear el acceso público en S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
2. En IAM, asigna al principal que utilizará el backend permisos de lectura y escritura para los archivos de facturas y los comprobantes de pago. Sustituye `TU_BUCKET` por el nombre elegido. Si usas una clave de cifrado propia de KMS, configura también los permisos de esa clave para el principal. [Políticas de identidad para S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/example-policies-s3.html)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": [
        "arn:aws:s3:::TU_BUCKET/invoice-files/*",
        "arn:aws:s3:::TU_BUCKET/payment-proofs/*"
      ]
    }
  ]
}
```

La subida viaja del navegador a la API y de la API a S3. La descarga se abre como navegación desde una redirección de la API, por lo que este flujo funciona con el bucket sin reglas CORS.

## Configurar el backend

En el entorno donde corre FastAPI, define `S3_BUCKET` y `AWS_REGION`. Boto3 obtiene las credenciales del entorno de ejecución. Si proporcionas credenciales mediante variables, usa `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`, más `AWS_SESSION_TOKEN` cuando sean temporales. Configúralas en los secretos del backend. [Credenciales de Boto3](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html)

Aplica `alembic upgrade head` y reinicia la API para cargar la configuración. En una factura de prueba, carga un documento como SuperAdmin, recarga la ficha y abre su descarga. La carga y descarga requieren una configuración válida. El historial de facturas y los metadatos siguen disponibles mientras se configura el bucket.

Con una cuenta de propietario de prueba, envía un reporte con comprobante desde el estado de cuenta. Abre la bandeja «Reportes de pago» del edificio como SuperAdmin y descarga el archivo antes de decidir sobre el reporte.

## Reintentos y recuperación

Cada archivo se confirma por separado. Reenviar el mismo contenido y tipo para una factura reutiliza la entrada y la clave. Si el almacenamiento acepta el archivo pero la operación queda sin confirmar, la ficha solo muestra metadatos confirmados y el reintento idempotente utiliza la misma clave.

La migración protege los metadatos existentes al revertir. Antes de bajar de revisión con adjuntos registrados, conserva una copia de los metadatos y objetos para migrarlos juntos.
