import os
from pathlib import Path

import lark_oapi as lark
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / "backend" / ".env")

# P2ImMessageReceiveV1 receives v2.0 messages; CustomizedEvent handles v1.0 events.


def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    payload = lark.JSON.marshal(data, indent=4)
    print(f"[do_p2_im_message_receive_v1], data: {payload}")


def do_message_event(data: lark.CustomizedEvent) -> None:
    payload = lark.JSON.marshal(data, indent=4)
    print(f"[do_customized_event], type: message, data: {payload}")


event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .register_p1_customized_event("out_approval", do_message_event)
    .build()
)


def main():
    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError(
            "Missing LARK_APP_ID or LARK_APP_SECRET in backend/.env"
        )

    cli = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )
    cli.start()


if __name__ == "__main__":
    main()
