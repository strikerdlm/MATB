// Author: Dr Diego Malpica MD
// Todo el contenido visible para el participante, en español (es-CO).
// El registro sigue el de los instrumentos validados (nasatlx_es).

export const ES = {
  common: {
    practice: "Práctica",
    practiceDone: "Fin de la práctica. Ahora comienza la prueba real.",
    ready: "Prepárese…",
    continue: "Continuar",
    start: "Comenzar",
    subtestOf: (i: number, n: number) => `Prueba ${i} de ${n}`,
    done: "Ha completado todas las pruebas. Gracias.",
    saving: "Guardando resultados…",
  },
  simpleRt: {
    title: "Tiempo de reacción simple",
    instructions:
      "Cuando aparezca el círculo verde, presione la BARRA ESPACIADORA lo más rápido posible. " +
      "No presione antes de que aparezca.",
  },
  choiceRt: {
    title: "Tiempo de reacción de elección",
    instructions:
      "Aparecerá una flecha apuntando a la IZQUIERDA o a la DERECHA. " +
      "Presione la tecla de flecha correspondiente (← o →) lo más rápido posible.",
  },
  nback: {
    title: "Memoria de trabajo (2-atrás)",
    instructions:
      "Verá letras una por una. Presione la BARRA ESPACIADORA cuando la letra " +
      "actual sea IGUAL a la que apareció DOS posiciones antes. " +
      "Ejemplo: en la secuencia C…G…C, la segunda C es un acierto.",
  },
  tracking: {
    title: "Seguimiento con el ratón",
    instructions:
      "Un punto se moverá por la pantalla. Mantenga el cursor del ratón " +
      "lo más cerca posible del punto en todo momento, hasta que termine el tiempo.",
  },
} as const;
