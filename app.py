"""
app.py
Streamlit front-end for the Intelligent Voice-Based Shopping Assistant.

Run with:
    streamlit run app.py

Pipeline:
    Upload audio -> ffmpeg -> WAV -> Whisper -> Text -> NLP -> Cart update -> UI
"""

import sqlite3

import streamlit as st

from audio_utils import process_audio_file
from nlp_engine import parse_command

DB_PATH = "shopping.db"

st.set_page_config(page_title="AI Shopping Assistant", page_icon="🛒", layout="centered")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_products(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM products").fetchall()


def get_product_by_name(conn, name: str):
    return conn.execute("SELECT * FROM products WHERE name = ?", (name,)).fetchone()


def add_to_cart(conn, product_id: int, quantity: float) -> None:
    existing = conn.execute(
        "SELECT * FROM cart WHERE product_id = ?", (product_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE cart SET quantity = quantity + ? WHERE product_id = ?",
            (quantity, product_id),
        )
    else:
        conn.execute(
            "INSERT INTO cart (product_id, quantity) VALUES (?, ?)",
            (product_id, quantity),
        )
    conn.commit()


def update_cart_quantity(conn, product_id: int, quantity: float) -> None:
    conn.execute(
        "UPDATE cart SET quantity = ? WHERE product_id = ?", (quantity, product_id)
    )
    conn.commit()


def remove_from_cart(conn, product_id: int) -> None:
    conn.execute("DELETE FROM cart WHERE product_id = ?", (product_id,))
    conn.commit()


def get_cart_items(conn):
    return conn.execute("""
        SELECT c.id as cart_id, p.id as product_id, p.name, p.price, p.unit, c.quantity
        FROM cart c JOIN products p ON c.product_id = p.id
    """).fetchall()


def clear_cart(conn) -> None:
    conn.execute("DELETE FROM cart")
    conn.commit()


def checkout(conn) -> float:
    items = get_cart_items(conn)
    total = sum(item["price"] * item["quantity"] for item in items)
    if items:
        cur = conn.execute("INSERT INTO orders (total) VALUES (?)", (total,))
        order_id = cur.lastrowid
        for item in items:
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase) "
                "VALUES (?, ?, ?, ?)",
                (order_id, item["product_id"], item["quantity"], item["price"]),
            )
        clear_cart(conn)
        conn.commit()
    return total


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def execute_command(conn, text: str) -> str:
    """Runs NLP on the transcribed text and applies the resulting action(s).
    A single voice command can reference multiple products
    (e.g. "Add 2 kg rice and 1 litre milk"), so this may perform several
    cart updates and returns one combined status message.
    """
    product_names = [p["name"] for p in get_all_products(conn)]
    parsed_commands = parse_command(text, product_names)

    messages = []
    for parsed in parsed_commands:
        if parsed.intent == "add":
            if not parsed.product:
                messages.append(f"Couldn't figure out the product in: \"{parsed.raw_text}\"")
                continue
            product = get_product_by_name(conn, parsed.product)
            add_to_cart(conn, product["id"], parsed.quantity)
            messages.append(f"Added {parsed.quantity} {parsed.unit} of {parsed.product}.")

        elif parsed.intent == "remove":
            if not parsed.product:
                messages.append(f"Couldn't figure out which product to remove in: \"{parsed.raw_text}\"")
                continue
            product = get_product_by_name(conn, parsed.product)
            remove_from_cart(conn, product["id"])
            messages.append(f"Removed {parsed.product} from your cart.")

        elif parsed.intent == "update_quantity":
            if not parsed.product:
                messages.append("Couldn't figure out which product's quantity to change.")
                continue
            product = get_product_by_name(conn, parsed.product)
            update_cart_quantity(conn, product["id"], parsed.quantity)
            messages.append(f"Updated {parsed.product} quantity to {parsed.quantity} {parsed.unit}.")

        elif parsed.intent == "show_cart":
            messages.append("Here's your current cart:")

        elif parsed.intent == "checkout":
            total = checkout(conn)
            messages.append(f"Order placed! Total: ₹{total:.2f}" if total else "Your cart is empty.")

        else:
            messages.append("Sorry, I didn't understand that command. Try something like 'Add 2 kg rice'.")

    return " ".join(messages)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def main():
    st.title("🛒 AI Shopping Assistant")
    st.caption("Speak or upload a command like: \"Add 2 kg basmati rice and 1 litre milk\"")

    conn = get_connection()

    st.subheader("🎙️ Voice Command")

    input_mode = st.radio(
        "Choose input method",
        ["🎤 Record live", "📁 Upload audio file"],
        horizontal=True,
    )

    audio_bytes = None
    audio_suffix = ".wav"

    if input_mode == "🎤 Record live":
        mic_recording = st.audio_input("Click the microphone and speak your command")
        if mic_recording is not None:
            audio_bytes = mic_recording.getvalue()
            audio_suffix = ".wav"  # st.audio_input always returns WAV
    else:
        audio_file = st.file_uploader(
            "Upload an audio file (aac, mp3, m4a, wav)", type=["aac", "mp3", "m4a", "wav"]
        )
        if audio_file is not None:
            audio_bytes = audio_file.read()
            audio_suffix = "." + audio_file.name.split(".")[-1]

    typed_text = st.text_input("...or type a command instead (useful for quick testing)")

    col1, col2 = st.columns(2)
    with col1:
        process_audio_clicked = st.button("Process Audio", disabled=audio_bytes is None)
    with col2:
        process_text_clicked = st.button("Process Typed Command", disabled=not typed_text)

    status_message = None

    if process_audio_clicked and audio_bytes is not None:
        with st.spinner("Converting audio and transcribing with Whisper..."):
            temp_input_path = f"temp_input{audio_suffix}"
            with open(temp_input_path, "wb") as f:
                f.write(audio_bytes)
            try:
                transcribed_text = process_audio_file(temp_input_path)
                st.info(f"Transcribed: \"{transcribed_text}\"")
                status_message = execute_command(conn, transcribed_text)
            except Exception as e:
                status_message = f"Error processing audio: {e}"

    if process_text_clicked and typed_text:
        status_message = execute_command(conn, typed_text)

    if status_message:
        st.success(status_message)

    st.divider()
    st.subheader("🛒 Your Cart")

    cart_items = get_cart_items(conn)
    if not cart_items:
        st.write("Your cart is empty.")
    else:
        total = 0
        for item in cart_items:
            subtotal = item["price"] * item["quantity"]
            total += subtotal
            st.write(
                f"**{item['name']}** — {item['quantity']} {item['unit']} "
                f"× ₹{item['price']} = ₹{subtotal:.2f}"
            )
        st.markdown(f"### Total: ₹{total:.2f}")

        if st.button("✅ Checkout"):
            final_total = checkout(conn)
            st.success(f"Order placed! Total: ₹{final_total:.2f}")
            st.rerun()

    st.divider()
    with st.expander("📦 Browse all available products"):
        for p in get_all_products(conn):
            st.write(f"{p['name']} — ₹{p['price']} / {p['unit']}")

    conn.close()


if __name__ == "__main__":
    main()
