"""Unexpected GUI errors must fail tests instead of opening a modal alert."""
import pytest


@pytest.fixture(autouse=True)
def fail_on_ui_error(monkeypatch):
    from tkinter import messagebox
    errors=[]
    monkeypatch.setattr(messagebox,'showerror',lambda title,message,**kwargs:errors.append(str(message)))
    yield
    assert not errors, 'Unexpected UI error: '+ '; '.join(errors)
