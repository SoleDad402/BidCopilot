"""Extract form structure from DOM."""
from __future__ import annotations
from pydantic import BaseModel, Field

class FormField(BaseModel):
    field_id: str
    label: str
    field_type: str  # text, email, tel, select, checkbox, radio, textarea, file
    required: bool = False
    options: list[str] | None = None
    max_length: int | None = None
    placeholder: str | None = None
    current_value: str | None = None

class FormStructure(BaseModel):
    fields: list[FormField] = Field(default_factory=list)
    submit_selector: str | None = None
    is_multi_step: bool = False
    current_step: int = 1
    total_steps: int | None = None

class FormExtractor:
    async def extract(self, page) -> FormStructure:
        fields = []
        elements = await page.query_selector_all(
            "input:not([type=hidden]):not([type=submit]), select, textarea"
        )
        for elem in elements:
            tag = await elem.evaluate("el => el.tagName.toLowerCase()")
            input_type = await elem.get_attribute("type") or "text"
            name = await elem.get_attribute("name") or ""
            elem_id = await elem.get_attribute("id") or ""
            placeholder = await elem.get_attribute("placeholder") or ""
            required = await elem.get_attribute("required") is not None
            aria_label = await elem.get_attribute("aria-label") or ""

            label = ""
            if elem_id:
                label_elem = await page.query_selector(f"label[for='{elem_id}']")
                if label_elem:
                    label = await label_elem.inner_text()
            if not label:
                label = aria_label or placeholder or name

            selector = f"#{elem_id}" if elem_id else f"[name='{name}']" if name else None
            if not selector:
                continue

            field = FormField(
                field_id=selector, label=label.strip(),
                field_type=input_type if tag == "input" else tag,
                required=required, placeholder=placeholder,
            )

            if tag == "select":
                options = await elem.query_selector_all("option")
                field.options = [await opt.inner_text() for opt in options]

            fields.append(field)

        file_inputs = await page.query_selector_all("input[type=file]")
        for fi in file_inputs:
            fi_id = await fi.get_attribute("id") or ""
            fi_name = await fi.get_attribute("name") or ""
            selector = f"#{fi_id}" if fi_id else f"[name='{fi_name}']" if fi_name else None
            if selector:
                fields.append(FormField(field_id=selector, label="File upload", field_type="file"))

        return FormStructure(fields=fields)
