const channel = [
  [83.870, 21.535],
  [83.881, 21.509],
  [83.908, 21.484],
  [83.939, 21.469],
  [83.962, 21.445],
  [83.982, 21.418],
  [84.022, 21.396],
  [84.068, 21.374],
  [84.102, 21.348]
]

const keyframes = [
  {
    minute: 0,
    reach: 0,
    width: 0,
    depth: 0
  },
  {
    minute: 15,
    reach: 0.28,
    width: 0.007,
    depth: 2.1
  },
  {
    minute: 30,
    reach: 0.62,
    width: 0.015,
    depth: 5.3
  },
  {
    minute: 60,
    reach: 1,
    width: 0.027,
    depth: 8.4
  }
]

export const depthBands = [
  {
    id: 'shallow',
    minimum: 0,
    label: '0–1 m',
    color: '#25d8e5'
  },
  {
    id: 'moderate',
    minimum: 1,
    label: '1–3 m',
    color: '#368cf2'
  },
  {
    id: 'deep',
    minimum: 3,
    label: '3–6 m',
    color: '#7164f4'
  },
  {
    id: 'very-deep',
    minimum: 6,
    label: '6–9+ m',
    color: '#c28cff'
  }
]

function interpolatePoint(a, b, amount) {
  return [
    a[0] + (b[0] - a[0]) * amount,
    a[1] + (b[1] - a[1]) * amount
  ]
}

function pointAlongChannel(progress) {
  const value = Math.max(
    0,
    Math.min(1, progress)
  )

  const scaled =
    value * (channel.length - 1)

  const index = Math.min(
    channel.length - 2,
    Math.floor(scaled)
  )

  const amount =
    scaled - index

  return interpolatePoint(
    channel[index],
    channel[index + 1],
    amount
  )
}

function corridor(reach, width) {
  if (
    reach <= 0 ||
    width <= 0
  ) {
    return []
  }

  const samples = 42

  const left = []
  const right = []

  for (
    let index = 0;
    index < samples;
    index += 1
  ) {
    const progress =
      index / (samples - 1)

    const [
      lon,
      lat
    ] = pointAlongChannel(
      reach * progress
    )

    const bodyShape =
      0.72 +
      0.28 *
        Math.sin(
          Math.PI * progress
        )

    const startShape =
      Math.min(
        1,
        0.55 +
          progress * 4
      )

    const endShape =
      progress > 0.9
        ? Math.max(
            0.12,
            (1 - progress) /
              0.1
          )
        : 1

    const halfWidth =
      width *
      bodyShape *
      startShape *
      endShape

    left.push([
      lon - halfWidth,
      lat
    ])

    right.push([
      lon + halfWidth,
      lat
    ])
  }

  const ring = [
    ...left,
    ...right.reverse()
  ]

  ring.push([
    ...ring[0]
  ])

  return ring
}

function interpolateState(minute) {
  if (minute <= 0) {
    return {
      ...keyframes[0]
    }
  }

  let lower =
    keyframes[0]

  let upper =
    keyframes[
      keyframes.length - 1
    ]

  for (
    let index = 1;
    index <
    keyframes.length;
    index += 1
  ) {
    if (
      minute <=
      keyframes[index].minute
    ) {
      lower =
        keyframes[index - 1]

      upper =
        keyframes[index]

      break
    }
  }

  if (
    minute >=
    keyframes[
      keyframes.length - 1
    ].minute
  ) {
    return {
      ...keyframes[
        keyframes.length - 1
      ]
    }
  }

  const amount =
    (minute -
      lower.minute) /
    (upper.minute -
      lower.minute)

  return {
    minute,
    reach:
      lower.reach +
      (upper.reach -
        lower.reach) *
        amount,
    width:
      lower.width +
      (upper.width -
        lower.width) *
        amount,
    depth:
      lower.depth +
      (upper.depth -
        lower.depth) *
        amount
  }
}

export function getFloodVisual(input) {
  const minute =
    Number.isFinite(
      Number(input)
    )
      ? Math.max(
          0,
          Math.min(
            60,
            Number(input)
          )
        )
      : 0

  if (minute <= 0) {
    return {
      minute: 0,
      depth: 0,
      ring: [],
      bands: [],
      risk: 'Advisory'
    }
  }

  const state =
    interpolateState(minute)

  const bands = []

  const shallow =
    corridor(
      state.reach,
      state.width
    )

  if (shallow.length) {
    bands.push({
      ...depthBands[0],
      ring: shallow
    })
  }

  if (state.depth >= 1) {
    bands.push({
      ...depthBands[1],
      ring: corridor(
        state.reach * 0.92,
        state.width * 0.66
      )
    })
  }

  if (state.depth >= 3) {
    bands.push({
      ...depthBands[2],
      ring: corridor(
        state.reach * 0.80,
        state.width * 0.40
      )
    })
  }

  if (state.depth >= 6) {
    bands.push({
      ...depthBands[3],
      ring: corridor(
        state.reach * 0.62,
        state.width * 0.21
      )
    })
  }

  return {
    minute,
    depth:
      state.depth,
    ring:
      shallow,
    bands,
    risk:
      state.depth >= 3
        ? 'Critical'
        : 'Warning'
  }
}

export function validFloodBounds(ring) {
  if (
    !Array.isArray(ring) ||
    ring.length < 4
  ) {
    return null
  }

  const valid =
    ring.every(
      point =>
        Array.isArray(point) &&
        point.length >= 2 &&
        Number.isFinite(
          Number(point[0])
        ) &&
        Number.isFinite(
          Number(point[1])
        )
    )

  if (!valid) {
    return null
  }

  const longitudes =
    ring.map(
      point =>
        Number(point[0])
    )

  const latitudes =
    ring.map(
      point =>
        Number(point[1])
    )

  const west =
    Math.min(
      ...longitudes
    ) - 0.015

  const east =
    Math.max(
      ...longitudes
    ) + 0.015

  const south =
    Math.min(
      ...latitudes
    ) - 0.015

  const north =
    Math.max(
      ...latitudes
    ) + 0.015

  if (
    ![
      west,
      east,
      south,
      north
    ].every(
      Number.isFinite
    )
  ) {
    return null
  }

  if (
    west >= east ||
    south >= north
  ) {
    return null
  }

  return {
    west,
    east,
    south,
    north
  }
}