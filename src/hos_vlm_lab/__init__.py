def main() -> None:
    import uvicorn
    from dotenv import load_dotenv
    from .app import create_app

    load_dotenv(".env", override=False, encoding="utf-8-sig")
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
