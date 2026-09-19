# -*- coding: utf-8 -*-
"""Chat en tiempo real para JD Studios.
Servidor WebSocket + estaticos en Python puro (sin dependencias).

Uso:  python chat_server.py [puerto]
      Cliente:  http://localhost:8000
      Admin:    http://localhost:8000/?admin=jdstudios2024
"""
import base64
import hashlib
import json
import mimetypes
import os
import socket
import struct
import sys
import threading
import time
import traceback
from collections import deque

DIR = os.path.dirname(os.path.abspath(__file__))
PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
CLAVE_ADMIN = "jdstudios2024"
SECRETO = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
RUTA_DEBUG = os.path.join(DIR, "chat_debug.log")
mimetypes.add_type("text/html; charset=utf-8", ".html")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("image/svg+xml", ".svg")

# ---------- Estado ----------
console_log = print
LOCK = threading.Lock()
clientes = {}          # id -> {'sock', 'rol', 'nombre', 'i'}
historial = {}         # id -> deque de {'de', 'm', 'h'}
ids_seq = 0


def ahora():
    return time.strftime("%H:%M")


def nuevo_id():
    global ids_seq
    ids_seq += 1
    return "c%d" % ids_seq


def registrar_error(ex):
    try:
        with open(RUTA_DEBUG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%H:%M:%S] ") + "".join(traceback.format_exception(type(ex), ex, ex.__traceback__)) + "\n")
    except OSError:
        pass


# ---------- Frames WebSocket ----------
def enviar(ws, obj):
    """Envia un frame WebSocket de texto (sin enmascarar)."""
    try:
        datos = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        marco = bytearray([0x81])
        ln = len(datos)
        if ln < 126:
            marco.append(ln)
        elif ln < 65536:
            marco.append(126)
            marco += struct.pack(">H", ln)
        else:
            marco.append(127)
            marco += struct.pack(">Q", ln)
        marco += datos
        ws.sendall(marco)
    except OSError:
        pass


def enviar_pong(ws):
    try:
        ws.sendall(bytes([0x8A, 0x00]))
    except OSError:
        pass


# ---------- Logica de negocio ----------
def limpiar_cliente(cid):
    with LOCK:
        cl = clientes.pop(cid, None)
    if cl is None:
        return
    console_log("Desconectado:", cid)
    a_todos_admins({"t": "sale", "id": cid})


def nro_visitantes():
    with LOCK:
        return sum(1 for c in clientes.values() if c["rol"] != "admin")


def lista_chats():
    """Resumen para el admin."""
    res = []
    with LOCK:
        for cid, c in list(clientes.items()):
            if c["rol"] == "admin":
                continue
            hist = historial.get(cid, [])
            ultimo = hist[-1]["m"] if hist else ""
            res.append({"id": cid, "nombre": c["nombre"], "ultimo": ultimo})
        res.sort(key=lambda x: x["id"])
    return res


def a_todos_admins(obj, excepto=None):
    with LOCK:
        lista = [c for c in clientes.values() if c["rol"] == "admin"]
    for c in lista:
        if excepto is not None and c.get("i") == excepto:
            continue
        enviar(c["sock"], obj)


def registrar_ws(conn, cid, direccion):
    global ids_seq
    with LOCK:
        clientes[cid] = {"sock": conn, "rol": "visitante", "nombre": "Visitante", "i": cid}
        historial.setdefault(cid, deque(maxlen=200))
    console_log("Conectado:", cid, "->", direccion)
    enviar(conn, {"t": "hola", "id": cid})
    a_todos_admins({"t": "entra", "id": cid})


def atender_ws(conn, cid):
    """Lee frames hasta que se desconecte."""
    while True:
        try:
            b0 = conn.recv(1)
            if not b0:
                break
            b1 = conn.recv(1)
            opcode = b0[0] & 0x0F
            ln = b1[0] & 0x7F
            enmascarado = b1[0] & 0x80
            if ln == 126:
                ln = struct.unpack(">H", conn.recv(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", conn.recv(8))[0]
            if opcode == 0x8:  # cerrar
                break
            if opcode == 0x9:  # ping
                enviar_pong(conn)
                continue
            mascara = conn.recv(4) if enmascarado else None
            resto = ln
            trozos = []
            while resto > 0:
                trozo = conn.recv(min(resto, 65536))
                if not trozo:
                    raise ConnectionError("cerrado")
                trozos.append(trozo)
                resto -= len(trozo)
            carga = b"".join(trozos)
            if mascara:
                carga = bytes(c ^ mascara[i % 4] for i, c in enumerate(carga))
            if opcode == 0x1:
                try:
                    gestionar(cid, json.loads(carga.decode("utf-8")))
                except Exception as ex:
                    registrar_error(ex)
        except Exception:
            registrar_error(sys.exc_info()[1])
            break
    try:
        conn.close()
    except OSError:
        pass
    limpiar_cliente(cid)


def gestionar(cid, msg):
    t = msg.get("t")
    with LOCK:
        cl = clientes.get(cid)
    if cl is None:
        return

    if t == "hello":  # intenta ser admin
        if msg.get("clave") == CLAVE_ADMIN:
            cl["rol"] = "admin"
            cl["nombre"] = "Admin"
            console_log("Admin conectado:", cid)
            with LOCK:
                hist_plano = {k: list(v) for k, v in historial.items()}
            enviar(cl["sock"], {"t": "listo", "total": nro_visitantes(), "chats": lista_chats(), "hist": hist_plano})
            a_todos_admins({"t": "presencia", "total": nro_visitantes()}, excepto=cid)
        else:
            enviar(cl["sock"], {"t": "clave_mala"})
        return

    if t == "nombre":
        cl["nombre"] = (msg.get("m") or "").strip()[:30] or "Visitante"
        return

    if t == "chat":  # mensaje de un visitante
        texto = (msg.get("m") or "").strip()[:800]
        if not texto:
            return
        m = {"de": "tu", "m": texto, "h": ahora()}
        with LOCK:
            hist = historial.setdefault(cid, deque(maxlen=200))
            hist.append(m)
        console_log("Mensaje de", cl["nombre"], "->", texto)
        a_todos_admins({"t": "entrante", "id": cid, "nombre": cl["nombre"], "m": texto, "h": m["h"]})
        return

    if t == "respuesta":  # respuesta del admin a un visitante
        if cl["rol"] != "admin":
            return
        cid_dest = msg.get("id")
        texto = (msg.get("m") or "").strip()[:800]
        if not cid_dest or not texto:
            return
        with LOCK:
            dest = clientes.get(cid_dest)
            hist = historial.setdefault(cid_dest, deque(maxlen=200))
            hist.append({"de": "yo", "m": texto, "h": ahora()})
        m_final = {"de": "yo", "m": texto, "h": ahora()}
        if dest:
            enviar(dest["sock"], {"t": "respuesta", "m": texto, "h": m_final["h"]})
        console_log("Respuesta del admin a", cid_dest, "->", texto)
        a_todos_admins({"t": "sinc", "id": cid_dest, "m": texto, "h": m_final["h"], "de": "yo"}, excepto=cid)
        return


# ---------- Servidor ----------
def servir_http(conn, ruta):
    p = ruta.split("?")[0]
    if p in ("", "/"):
        p = "/index.html"
    ruta_abs = os.path.normpath(os.path.join(DIR, p.lstrip("/")))
    if not ruta_abs.startswith(DIR) or not os.path.isfile(ruta_abs):
        conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 9\r\nConnection: close\r\n\r\nnot found")
        return
    with open(ruta_abs, "rb") as f:
        cuerpo = f.read()
    tipo = mimetypes.guess_type(ruta_abs)[0] or "application/octet-stream"
    cab = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "Cache-Control: no-cache\r\n"
        "Connection: close\r\n\r\n" % (tipo, len(cuerpo))
    )
    try:
        conn.sendall(cab.encode() + cuerpo)
    except OSError:
        pass


def aceptar_ws(conn, cabeceras):
    clave = cabeceras.get("sec-websocket-key")
    if not clave:
        conn.close()
        return
    aceptar = base64.b64encode(hashlib.sha1((clave + SECRETO).encode()).digest()).decode()
    resp = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n\r\n" % aceptar
    )
    conn.sendall(resp.encode())
    cid = nuevo_id()
    registrar_ws(conn, cid, conn.getpeername())
    atender_ws(conn, cid)


def atender_conexion(conn):
    conn.settimeout(8)
    datos = b""
    try:
        while b"\r\n\r\n" not in datos:
            t = conn.recv(4096)
            if not t:
                return
            datos += t
            if len(datos) > 65536:
                return
        encabezado, _, _ = datos.partition(b"\r\n\r\n")
        lineas = encabezado.decode("latin-1").split("\r\n")
        primera = lineas[0].split(" ")
        if len(primera) < 2:
            return
        metodo, ruta = primera[0], primera[1]
        cabeceras = {}
        for ln in lineas[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                cabeceras[k.strip().lower()] = v.strip()
    except Exception:
        return
    finally:
        conn.settimeout(None)

    if metodo == "GET" and cabeceras.get("upgrade", "").lower() == "websocket":
        aceptar_ws(conn, cabeceras)
    elif metodo == "GET":
        servir_http(conn, ruta)
    else:
        try:
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except OSError:
            pass


class ServidorChat:
    def __init__(self, host, puerto):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, puerto))
        self.sock.listen(128)
        self.running = True

    def servir(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=atender_conexion, args=(conn,), daemon=True).start()

    def cerrar(self):
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    url = "http://localhost:%d" % PUERTO
    print("=" * 52)
    print("  JD Studios - Chat en tiempo real")
    print("  Sitio:    %s" % url)
    print("  Admin:    %s/?admin=%s" % (url, CLAVE_ADMIN))
    print("  Cierra con Ctrl+C")
    print("=" * 52)
    srv = ServidorChat("0.0.0.0", PUERTO)
    try:
        srv.servir()
    except KeyboardInterrupt:
        srv.cerrar()