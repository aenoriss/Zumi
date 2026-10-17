# Zumi: cómics XR generados desde bocetos, para leer en grupo

## La idea

Un artista dibuja un cómic a mano, en boceto. Zumi lo convierte en un cómic terminado, con profundidad, voz, sonido y animación, que se lee dentro de un visor Meta Quest 3 junto a otras personas. Participamos en la competencia de desarrolladores de Meta, con entrega a mediados de noviembre de 2026. Por eso usamos modelos de Meta en todo lo que se pueda.

## Qué hace el pipeline de IA, viñeta por viñeta

1. Un modelo de visión lee el boceto: entiende la escena, detecta los globos de diálogo, transcribe el texto manuscrito y adivina quién habla.
2. Borra los globos del boceto y redibuja la viñeta en el estilo elegido por el autor. El estilo se define con un preset, con texto libre o con imágenes de referencia, y se mantiene igual en todo el cómic. El boceto manda la composición; el estilo solo cambia el acabado.
3. Recorta la imagen en capas (personajes, fondo, objetos) y rellena lo que queda detrás de cada recorte. Cada capa recibe una profundidad. En el visor, al mover la cabeza, las capas se desplazan a distinta velocidad: eso es el parallax, el efecto de "papel recortado" en 3D.
4. Los diálogos se convierten en texto editable y se graban con una voz distinta por personaje. El autor elige o describe la voz de cada personaje una sola vez por cómic.
5. Genera un sonido ambiente por viñeta a partir del clima de la escena (lluvia, sirenas, multitud) y una música instrumental por escena.
6. Si el autor escribe una indicación ("llueve, el letrero parpadea, la capa se mueve con el viento"), la IA la traduce a animaciones simples sobre las capas de la viñeta.
7. Algunas viñetas pueden ser inmersivas: un panorama 360 que te rodea, o una escena 3D que un modelo de lenguaje construye solo, manejando Blender.

## La herramienta web

Subís los bocetos, elegís el estilo, confirmás el reparto de personajes y sus voces, y la IA procesa cada viñeta en paralelo. Después corregís lo que haga falta: texto de un diálogo, quién lo dice, posición de un globo, unir dos capas, ajustar profundidad, regenerar una viñeta, cambiar el orden. Hay una vista previa con parallax en el navegador. Cuando está listo, publicás el capítulo.

## La experiencia en el visor

- Realidad mixta: ves tu habitación y las viñetas flotan frente a vos, una a la vez, en carrusel.
- Lectura compartida: al abrir un capítulo entrás a una sala con hasta 8 lectores. El cómic avanza solo, con un tiempo por viñeta calculado a partir de las voces. Cualquiera puede proponer pausa, y se pausa si la mayoría acepta.
- Los otros lectores son esferas brillantes repartidas por la habitación. Hablás por voz, y además tenés frases cortas predefinidas (estilo Hearthstone) que aparecen como globos de cómic.
- Todo se controla con las manos, sin controles físicos.
- Al terminar un capítulo, cada uno elige: seguir al siguiente con el mismo grupo, o volver a la biblioteca.

## Lo que necesitamos del artista

- Bocetos a lápiz o tinta, uno por viñeta, con los diálogos escritos a mano dentro del globo.
- Referencias visuales del estilo final que quiere.
- Un capítulo de prueba de unas 10 páginas para el demo. Procesarlo cuesta alrededor de 6 dólares en IA.

**Estructura**: autor → cómic (serie, con estilo y reparto fijos) → capítulo (un archivo `.zumi` con todo adentro).

---

# Flujo completo, del creador al lector

## Parte 1: el creador, en la web

1. **Cuenta y cómic.** Entrás a la web, creás tu cuenta y un cómic nuevo: título, portada, descripción.
2. **Estilo.** Definís el estilo visual del cómic una sola vez: elegís un preset, escribís una descripción, o subís entre 1 y 5 imágenes de referencia. Se puede combinar las tres cosas.
3. **Nuevo capítulo.** Dentro del cómic creás un capítulo y subís los bocetos, uno por viñeta, en orden.
4. **Procesamiento.** Apretás "Generar". Cada viñeta se procesa en paralelo y va apareciendo en el editor a medida que termina. Mientras tanto ya podés trabajar sobre las primeras.
5. **Reparto.** Al terminar la lectura de los bocetos, la IA te muestra el reparto que detectó: lista de personajes y qué diálogos dice cada uno. Confirmás, renombrás o fusionás personajes. A cada uno le asignás una voz: elegís de una galería o la describís con palabras ("marinero viejo, voz áspera"). Escuchás una línea de prueba. Las voces quedan guardadas en el cómic para todos los capítulos.
6. **Edición por viñeta.** Para cada viñeta podés:
   - Corregir el texto de un diálogo, cambiar quién lo dice, mover el globo.
   - Ver las capas que recortó la IA, unir dos que deberían ser una, acercar o alejar una capa.
   - Escribir una indicación de animación en lenguaje natural, ver el resultado en la vista previa, regenerar o borrar.
   - Marcar la viñeta como inmersiva: panorama 360 o escena 3D. Para la escena 3D la IA la construye y te muestra una vista previa.
   - Regenerar la imagen con un ajuste al texto o a las referencias si el resultado no te gusta.
   - Cambiar el orden de las viñetas o la duración de una viñeta.
7. **Vista previa.** Toda la edición se ve en una vista previa con parallax en el navegador: movés el mouse y las capas se desplazan, las animaciones corren, las voces suenan.
8. **Publicar.** Apretás "Publicar". El capítulo se empaqueta en un archivo `.zumi` y aparece en la biblioteca pública, en la web (galería con vista previa) y en el visor.

## Parte 2: el lector, en el Quest 3

1. **Entrar.** Abrís Zumi. Ves tu habitación (realidad mixta) y, flotando, la biblioteca: portadas de cómics. Todo se maneja con las manos: apuntás y hacés "pinch" (juntar índice y pulgar) para elegir.
2. **Elegir.** Elegís un cómic, después un capítulo. Cada capítulo muestra cuántas personas lo están leyendo ahora.
3. **Sala.** Al abrir el capítulo entrás automáticamente a una sala. Si hay gente leyendo ese capítulo, te sumás a la sala más llena que tenga lugar (máximo 8) y aparecés en la viñeta donde están ellos. Si no hay nadie, se abre una sala nueva desde la viñeta 1. También podés invitar amigos desde el menú de Quest, o unirte a un amigo que ya esté leyendo.
4. **Lectura.** La viñeta actual flota frente a vos a distancia de lectura, con la anterior y la siguiente como tarjetas pequeñas y atenuadas a los costados. Al mover la cabeza las capas se desplazan con profundidad. Los diálogos aparecen como globos y se escuchan con la voz de cada personaje. Suena el ambiente de la escena y una música de fondo. Si la viñeta tiene animación, se mueve.
5. **Avance.** El cómic avanza solo. Cada viñeta dura lo que duran sus voces más un margen de lectura. Todos en la sala ven la misma viñeta al mismo tiempo.
6. **Los demás.** Los otros lectores son esferas brillantes repartidas por tu habitación. Los escuchás por voz. Cada uno puede abrir un menú radial con un pinch y elegir una frase corta predefinida ("esperá", "¡no!", "jaja", "mirá eso"), que aparece como globo de cómic sobre su esfera y se escucha con voz.
7. **Pausa.** Si querés detenerte en una viñeta, abrís el menú y proponés pausa. Las esferas de los demás muestran la propuesta; si la mayoría acepta con un pinch, el cómic se congela. Para seguir, lo mismo: mayoría.
8. **Viñetas inmersivas.** Cuando llega una viñeta 360 o 3D, tu habitación desaparece y quedás dentro de la escena. Podés girar y mirar alrededor. Las esferas de los demás siguen ahí con vos. Dura más tiempo que una viñeta normal, y al terminar volvés a tu habitación.
9. **Final.** Al terminar el capítulo aparece una tarjeta con dos botones: "Seguir al próximo capítulo" (seguís con la misma sala) o "Volver a la biblioteca". Cada lector decide por su cuenta.
