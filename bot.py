import os
import logging
from datetime import datetime
from urllib.parse import quote

import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler,
)

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
SPREADSHEET_ID   = "1L9jj1K4fXSsPITAMjqt3_SBigw3l8ZDQhH3rcZZP_6g"
CREDENTIALS_FILE = "credentials.json"

SHEET_CLIENTES   = "CLIENTES"
SHEET_STOCK      = "STOCK"
SHEET_PRECIOS    = "CATALOGO_PRECIOS"
SHEET_VENTAS     = "VENTAS"

# Estados del ConversationHandler
ELEGIR_CLIENTE, ELEGIR_PRODUCTO, INGRESAR_CANTIDAD = range(3)

logging.basicConfig(level=logging.WARNING)

# ─────────────────────────────────────────────
#  ACCESO A GOOGLE SHEETS
# ─────────────────────────────────────────────
def _spreadsheet():
    credentials = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)

def cargar_clientes():
    ws = _spreadsheet().worksheet(SHEET_CLIENTES)
    return get_records(ws)

def cargar_stock():
    ws = _spreadsheet().worksheet(SHEET_STOCK)
    records = get_records(ws)
    return {r["Producto"]: r for r in records if r.get("Producto")}

def cargar_precios():
    ws = _spreadsheet().worksheet(SHEET_PRECIOS)
    records = get_records(ws)
    return {r["Producto"]: r for r in records if r.get("Producto")}

def ultimo_nro_pedido():
    ws  = _spreadsheet().worksheet(SHEET_VENTAS)
    col = ws.col_values(14)  # Columna N = Nro Pedido
    nums = [int(v) for v in col[1:] if str(v).isdigit()]
    return max(nums) if nums else 0

def guardar_fila_venta(fila: list):
    ws = _spreadsheet().worksheet(SHEET_VENTAS)
    ws.append_row(fila, value_input_option="USER_ENTERED")

def get_records(ws):
    """get_all_records tolerante a encabezados duplicados."""
    data = ws.get_all_values()
    if not data:
        return []
    headers = data[0]
    seen = {}
    unique = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique.append(h)
    return [dict(zip(unique, row)) for row in data[1:] if any(row)]

# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────
def fmt_precio(valor) -> str:
    try:
        n = float(str(valor).replace("$", "").replace(".", "").replace(",", "."))
        return f"${int(n):,}".replace(",", ".")
    except Exception:
        return str(valor)

def limpiar_precio(valor) -> float:
    try:
        return float(str(valor).replace("$", "").replace(".", "").replace(",", "."))
    except Exception:
        return 0.0

def link_whatsapp(telefono, mensaje: str) -> str:
    tel = str(telefono).strip().replace(" ", "").replace("-", "")
    if tel.startswith("0"):
        tel = tel[1:]
    if not tel.startswith("549"):
        tel = "549" + tel
    return f"https://wa.me/{tel}?text={quote(mensaje)}"

# ─────────────────────────────────────────────
#  COMANDOS DEL BOT
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Bot de Ventas — Grido & Frutos Secos*\n\n"
        "🛒 /nuevo      → Cargar un pedido\n"
        "📦 /stock      → Ver stock disponible\n"
        "⏳ /pendientes → Pedidos sin entregar\n"
        "✏️ /gestionar  → Cambiar estado de pedidos\n"
        "👥 /clientes   → Lista de clientes\n"
        "❌ /cancelar   → Cancelar operación actual",
        parse_mode="Markdown",
    )

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Cargando stock…")
    try:
        stock = cargar_stock()
        helados = [(k, v) for k, v in stock.items() if v.get("Tipo producto") == "Helados"]
        frutos  = [(k, v) for k, v in stock.items() if v.get("Tipo producto") != "Helados" and k]

        texto = "📦 *Stock actual*\n\n🍦 *HELADOS*\n"
        for nombre, d in helados:
            disp = int(d.get("Disponible") or 0)
            icono = "✅" if disp > 0 else "❌"
            texto += f"  {icono} {nombre}: *{disp}*\n"

        texto += "\n🥜 *FRUTOS SECOS*\n"
        for nombre, d in frutos:
            disp = int(d.get("Disponible") or 0)
            icono = "✅" if disp > 0 else "❌"
            texto += f"  {icono} {nombre}: *{disp}*\n"

        await msg.edit_text(texto, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Cargando pendientes…")
    try:
        ws       = _spreadsheet().worksheet(SHEET_VENTAS)
        records  = get_records(ws)
        reservas = [r for r in records if r.get("Estado") == "Reservado"]

        if not reservas:
            await msg.edit_text("✅ No hay pedidos pendientes.")
            return

        por_cliente: dict = {}
        for r in reservas:
            c = r.get("Cliente", "—")
            por_cliente.setdefault(c, []).append(r)

        texto = "⏳ *Pedidos Reservados*\n\n"
        for cliente, items in por_cliente.items():
            texto += f"👤 *{cliente}*\n"
            for it in items:
                texto += (
                    f"  • {it.get('Cantidad')}x {it.get('Producto')} "
                    f"— {fmt_precio(it.get('Total', 0))}\n"
                )
            texto += "\n"

        await msg.edit_text(texto, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def cmd_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Cargando…")
    try:
        clientes = cargar_clientes()
        texto = "👥 *Clientes*\n\n"
        for c in clientes:
            nombre  = c.get("Nombre", "")
            tel     = c.get("Telefono", "")
            manzana = c.get("Manzana", "")
            lote    = c.get("Lote", "")
            if nombre:
                texto += f"• *{nombre}*"
                if tel:
                    texto += f"  📱 {tel}"
                if manzana and lote:
                    texto += f"  🏠 M{manzana} L{lote}"
                texto += "\n"
        await msg.edit_text(texto, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ─────────────────────────────────────────────
#  NUEVO PEDIDO - Paso 1: Elegir cliente
# ─────────────────────────────────────────────

async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["items"] = []

    msg = await update.message.reply_text("⏳ Cargando clientes…")
    try:
        clientes = cargar_clientes()
        context.user_data["clientes"] = clientes

        teclado = []
        for c in clientes:
            nombre = c.get("Nombre", "").strip()
            if nombre:
                teclado.append([InlineKeyboardButton(nombre, callback_data=f"cli|{c['ID Cliente']}")])
        teclado.append([InlineKeyboardButton("✏️ Escribir nombre nuevo", callback_data="cli|_manual_")])

        await msg.edit_text(
            "👤 *¿Para quién es el pedido?*",
            reply_markup=InlineKeyboardMarkup(teclado),
            parse_mode="Markdown",
        )
        return ELEGIR_CLIENTE
    except Exception as e:
        await msg.edit_text(f"❌ Error al cargar clientes: {e}")
        return ConversationHandler.END

async def cb_elegir_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, valor = query.data.split("|", 1)

    if valor == "_manual_":
        await query.edit_message_text("✏️ Escribí el nombre del cliente:")
        return ELEGIR_CLIENTE

    clientes = context.user_data.get("clientes", [])
    cliente  = next((c for c in clientes if str(c["ID Cliente"]) == valor), None)
    if not cliente:
        await query.edit_message_text("❌ Cliente no encontrado.")
        return ConversationHandler.END

    context.user_data["cliente"] = cliente
    return await _mostrar_menu_productos(query, context)

async def msg_nombre_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.message.text.strip()
    context.user_data["cliente"] = {"Nombre": nombre, "Telefono": "", "ID Cliente": ""}
    return await _mostrar_menu_productos(update, context)

# ─────────────────────────────────────────────
#  PASO 2: Menú de productos
# ─────────────────────────────────────────────

async def _mostrar_menu_productos(origen, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock   = cargar_stock()
        precios = cargar_precios()
        context.user_data["stock"]   = stock
        context.user_data["precios"] = precios

        disponibles = [(k, v) for k, v in stock.items()
                       if int(v.get("Disponible") or 0) > 0]

        items   = context.user_data.get("items", [])
        cliente = context.user_data["cliente"]["Nombre"]

        texto = f"🛒 *Pedido para {cliente}*\n"
        if items:
            texto += "\n*Cargado hasta ahora:*\n"
            subtotal = 0
            for it in items:
                s = it["cantidad"] * it["precio"]
                subtotal += s
                texto += f"  • {it['cantidad']}x {it['producto']}: {fmt_precio(s)}\n"
            texto += f"  ─────────────\n  *Subtotal: {fmt_precio(subtotal)}*\n"

        texto += "\n📦 *Elegí un producto:*"

        teclado = []
        for nombre, d in disponibles:
            disp       = int(d.get("Disponible") or 0)
            tipo       = d.get("Tipo producto", "")
            emoji      = "🍦" if tipo == "Helados" else "🥜"
            precio_pub = limpiar_precio(precios.get(nombre, {}).get("Precio público", 0))
            teclado.append([InlineKeyboardButton(
                f"{emoji} {nombre}  (x{disp}) {fmt_precio(precio_pub)}",
                callback_data=f"prod|{nombre}",
            )])

        if items:
            teclado.append([InlineKeyboardButton("✅ Confirmar pedido", callback_data="accion|confirmar")])
        teclado.append([InlineKeyboardButton("❌ Cancelar", callback_data="accion|cancelar")])

        markup = InlineKeyboardMarkup(teclado)

        if hasattr(origen, "edit_message_text"):
            await origen.edit_message_text(texto, reply_markup=markup, parse_mode="Markdown")
        else:
            await origen.message.reply_text(texto, reply_markup=markup, parse_mode="Markdown")

        return ELEGIR_PRODUCTO

    except Exception as e:
        if hasattr(origen, "edit_message_text"):
            await origen.edit_message_text(f"❌ Error: {e}")
        else:
            await origen.message.reply_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def cb_elegir_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tipo, valor = query.data.split("|", 1)

    if tipo == "accion":
        if valor == "confirmar":
            return await _confirmar_y_guardar(query, context)
        else:
            await query.edit_message_text("❌ Pedido cancelado.")
            return ConversationHandler.END

    producto    = valor
    stock       = context.user_data.get("stock", {})
    precios     = context.user_data.get("precios", {})
    disp        = int(stock.get(producto, {}).get("Disponible") or 0)
    precio_pub  = limpiar_precio(precios.get(producto, {}).get("Precio público", 0))

    context.user_data["producto_seleccionado"] = producto
    context.user_data["precio_seleccionado"]   = precio_pub

    await query.edit_message_text(
        f"📦 *{producto}*\n"
        f"💰 Precio: {fmt_precio(precio_pub)}\n"
        f"📊 Disponible: *{disp}*\n\n"
        f"¿Cuántas unidades querés agregar?",
        parse_mode="Markdown",
    )
    return INGRESAR_CANTIDAD

async def msg_ingresar_cantidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    if not texto.isdigit() or int(texto) <= 0:
        await update.message.reply_text("⚠️ Ingresá un número entero mayor a 0:")
        return INGRESAR_CANTIDAD

    cantidad  = int(texto)
    producto  = context.user_data["producto_seleccionado"]
    precio    = context.user_data["precio_seleccionado"]
    stock     = context.user_data["stock"]
    disp      = int(stock.get(producto, {}).get("Disponible") or 0)

    if cantidad > disp:
        await update.message.reply_text(
            f"⚠️ Solo hay *{disp}* disponibles. Ingresá un número ≤ {disp}:",
            parse_mode="Markdown",
        )
        return INGRESAR_CANTIDAD

    items = context.user_data["items"]
    existente = next((i for i in items if i["producto"] == producto), None)
    if existente:
        existente["cantidad"] += cantidad
    else:
        tipo = stock.get(producto, {}).get("Tipo producto", "")
        items.append({"producto": producto, "cantidad": cantidad,
                      "precio": precio, "tipo": tipo})

    await update.message.reply_text(f"✅ Agregado: *{cantidad}x {producto}*", parse_mode="Markdown")
    return await _mostrar_menu_productos(update, context)

# ─────────────────────────────────────────────
#  PASO 3: Confirmar y guardar en Google Sheets
# ─────────────────────────────────────────────

async def _confirmar_y_guardar(query, context: ContextTypes.DEFAULT_TYPE):
    items   = context.user_data.get("items", [])
    cliente = context.user_data.get("cliente", {})

    if not items:
        await query.edit_message_text("⚠️ No hay productos en el pedido.")
        return ConversationHandler.END

    await query.edit_message_text("⏳ Guardando en Google Sheets…")

    try:
        fecha      = datetime.now().strftime("%d/%m/%Y")
        nro_pedido = ultimo_nro_pedido() + 1
        precios    = context.user_data.get("precios", {})
        stock      = context.user_data.get("stock", {})
        total_gral = sum(i["cantidad"] * i["precio"] for i in items)

        for item in items:
            prod    = item["producto"]
            cant    = item["cantidad"]
            precio  = item["precio"]
            total   = cant * precio
            tipo    = item["tipo"]
            disp    = int(stock.get(prod, {}).get("Disponible") or 0)
            chequeo = "OK" if disp >= cant else "SIN STOCK"
            m_unit  = limpiar_precio(precios.get(prod, {}).get("Margen unitario", 0))
            m_total = m_unit * cant

            fila = [
                fecha,                        # A: Fecha
                cliente.get("Nombre", ""),    # B: Cliente
                tipo,                         # C: Categoría
                prod,                         # D: Producto
                cant,                         # E: Cantidad
                precio,                       # F: Precio unitario
                total,                        # G: Total
                "Reservado",                  # H: Estado
                disp,                         # I: Stock disponible
                chequeo,                      # J: Chequeo
                m_total,                      # K: Margen total
                m_unit,                       # L: Margen unitario
                "",                           # M: WhatsApp
                nro_pedido,                   # N: Nro Pedido
                "", "", "",                   # O, P, Q: Cubre, Queda, Saldo
            ]
            guardar_fila_venta(fila)

        lineas = "\n".join(
            f"  • {i['cantidad']}x {i['producto']}: {fmt_precio(i['cantidad'] * i['precio'])}"
            for i in items
        )
        nombre_cliente = cliente.get("Nombre", "")
        mensaje_wa = (
            f"Hola {nombre_cliente}! 🍦\n"
            f"Tu pedido #{nro_pedido}:\n"
            f"{lineas}\n"
            f"💰 Total: {fmt_precio(total_gral)}\n"
            f"Avisame cuando pasás a buscar 😊"
        )

        telefono = cliente.get("Telefono", "") or ""
        url_wa   = link_whatsapp(telefono, mensaje_wa) if telefono else None

        resumen = (
            f"✅ *Pedido #{nro_pedido} guardado!*\n\n"
            f"👤 {nombre_cliente}\n"
            f"{lineas}\n"
            f"─────────────\n"
            f"💰 *Total: {fmt_precio(total_gral)}*"
        )

        teclado = []
        if url_wa:
            teclado.append([InlineKeyboardButton("📱 Enviar por WhatsApp", url=url_wa)])

        await query.edit_message_text(
            resumen,
            reply_markup=InlineKeyboardMarkup(teclado) if teclado else None,
            parse_mode="Markdown",
        )

    except Exception as e:
        await query.edit_message_text(f"❌ Error al guardar: {e}")

    return ConversationHandler.END

async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Operación cancelada.")
    return ConversationHandler.END

# ─────────────────────────────────────────────
#  /gestionar — Cambiar estado de pedidos
# ─────────────────────────────────────────────

ESTADOS = ["Reservado", "Entregado", "Pagado", "Cancelado"]

async def cmd_gestionar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra pedidos agrupados por número para cambiar su estado."""
    msg = await update.message.reply_text("Cargando pedidos...")
    try:
        ws      = _spreadsheet().worksheet(SHEET_VENTAS)
        records = get_records(ws)

        # Agrupar por Nro Pedido, mostrar solo los no Pagados/Cancelados
        pedidos = {}
        for i, r in enumerate(records, start=2):  # fila real en sheet (header=1)
            nro = str(r.get("Nro Pedido", "")).strip()
            if not nro:
                continue
            estado = r.get("Estado", "")
            if estado in ("Pagado", "Cancelado", "Entregado"):
                continue
            if nro not in pedidos:
                pedidos[nro] = {"cliente": r.get("Cliente", ""), "estado": estado,
                                "items": [], "filas": []}
            pedidos[nro]["items"].append(
                f"{r.get('Cantidad')}x {r.get('Producto')}"
            )
            pedidos[nro]["filas"].append(i)

        if not pedidos:
            await msg.edit_text("No hay pedidos activos.")
            return

        teclado = []
        for nro, d in sorted(pedidos.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=True):
            resumen = ", ".join(d["items"][:2])
            if len(d["items"]) > 2:
                resumen += f" +{len(d['items'])-2} más"
            teclado.append([InlineKeyboardButton(
                f"#{nro} {d['cliente']} — {d['estado']} | {resumen}",
                callback_data=f"gest|{nro}"
            )])

        await msg.edit_text(
            "Toca un pedido para cambiar su estado:",
            reply_markup=InlineKeyboardMarkup(teclado)
        )
    except Exception as e:
        await msg.edit_text(f"Error: {e}")

async def cb_gestionar_pedido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra botones de estado para el pedido seleccionado."""
    query = update.callback_query
    await query.answer()

    partes = query.data.split("|")
    accion = partes[0]

    if accion == "gest":
        nro = partes[1]
        teclado = [[InlineKeyboardButton(e, callback_data=f"setestado|{nro}|{e}")]
                   for e in ESTADOS]
        teclado.append([InlineKeyboardButton("< Volver", callback_data="gest_volver")])
        await query.edit_message_text(
            f"Pedido #{nro} — elegí el nuevo estado:",
            reply_markup=InlineKeyboardMarkup(teclado)
        )

    elif accion == "setestado":
        nro, nuevo_estado = partes[1], partes[2]
        try:
            ws      = _spreadsheet().worksheet(SHEET_VENTAS)
            records = get_records(ws)
            filas_actualizadas = 0
            for i, r in enumerate(records, start=2):
                if str(r.get("Nro Pedido", "")).strip() == nro:
                    ws.update_cell(i, 8, nuevo_estado)  # columna H = Estado
                    filas_actualizadas += 1
            teclado = [[InlineKeyboardButton("Ver todos los pedidos", callback_data="gest_lista")]]
            await query.edit_message_text(
                f"Pedido #{nro} actualizado a *{nuevo_estado}*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(teclado)
            )
        except Exception as e:
            await query.edit_message_text(f"Error al actualizar: {e}")

    elif accion in ("gest_volver", "gest_lista"):
        # Mostrar lista de pedidos activos
        ws      = _spreadsheet().worksheet(SHEET_VENTAS)
        records = get_records(ws)
        pedidos = {}
        for i, r in enumerate(records, start=2):
            nro = str(r.get("Nro Pedido", "")).strip()
            if not nro:
                continue
            estado = r.get("Estado", "")
            if estado in ("Pagado", "Cancelado", "Entregado"):
                continue
            if nro not in pedidos:
                pedidos[nro] = {"cliente": r.get("Cliente", ""), "estado": estado, "items": []}
            pedidos[nro]["items"].append(f"{r.get('Cantidad')}x {r.get('Producto')}")
        if not pedidos:
            await query.edit_message_text("No hay pedidos activos.")
            return
        teclado = []
        for nro, d in sorted(pedidos.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=True):
            resumen = ", ".join(d["items"][:2])
            if len(d["items"]) > 2:
                resumen += f" +{len(d['items'])-2} mas"
            teclado.append([InlineKeyboardButton(
                f"#{nro} {d['cliente']} - {d['estado']} | {resumen}",
                callback_data=f"gest|{nro}"
            )])
        await query.edit_message_text(
            "Toca un pedido para cambiar su estado:",
            reply_markup=InlineKeyboardMarkup(teclado)
        )

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

import asyncio

def main():
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("nuevo", cmd_nuevo)],
        states={
            ELEGIR_CLIENTE: [
                CallbackQueryHandler(cb_elegir_cliente, pattern=r"^cli\|"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_nombre_manual),
            ],
            ELEGIR_PRODUCTO: [
                CallbackQueryHandler(cb_elegir_producto, pattern=r"^prod\|"),
                CallbackQueryHandler(cb_elegir_producto, pattern=r"^accion\|"),
            ],
            INGRESAR_CANTIDAD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, msg_ingresar_cantidad),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cmd_cancelar)],
    )

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("stock",      cmd_stock))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("clientes",   cmd_clientes))
    app.add_handler(CommandHandler("gestionar",  cmd_gestionar))
    app.add_handler(CallbackQueryHandler(cb_gestionar_pedido, pattern=r"^(gest|setestado|gest_volver|gest_lista)"))
    app.add_handler(conv)

    print("Bot iniciado. Ctrl+C para detener.")
    app.run_polling()

if __name__ == "__main__":
    main()
