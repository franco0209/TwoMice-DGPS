import { useCallback, useEffect, useRef, useState } from 'react'

const MAX = 1800 // épocas por receptor en memoria (30 min a 1 Hz)

/** Mantiene la conexión WebSocket con /api/gps/ws y acumula las épocas. */
export function useAcquisition() {
  const buf = useRef({ ref: [], rover: [] })
  const dirty = useRef(false)
  const [hist, setHist] = useState({ ref: [], rover: [] })
  const [status, setStatus] = useState(null)
  const [online, setOnline] = useState(false)

  useEffect(() => {
    let ws
    let timer
    let closed = false
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/gps/ws`)
      ws.onopen = () => setOnline(true)
      ws.onclose = () => {
        setOnline(false)
        if (!closed) timer = setTimeout(connect, 2000)
      }
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data)
        if (msg.epoch) {
          const list = buf.current[msg.epoch.rx]
          if (list) {
            list.push(msg.epoch)
            if (list.length > MAX) list.shift()
            dirty.current = true
          }
        }
        if (msg.status) setStatus(msg.status)
      }
    }
    connect()
    const flush = setInterval(() => {
      if (dirty.current) {
        dirty.current = false
        setHist({ ref: [...buf.current.ref], rover: [...buf.current.rover] })
      }
    }, 300)
    return () => {
      closed = true
      clearTimeout(timer)
      clearInterval(flush)
      ws?.close()
    }
  }, [])

  const reset = useCallback(() => {
    buf.current = { ref: [], rover: [] }
    setHist({ ref: [], rover: [] })
  }, [])

  return { hist, status, online, reset }
}
