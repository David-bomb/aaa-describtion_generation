import json
import unittest

from app.prompt import parse_params_json, render_prompt


class PromptTests(unittest.TestCase):
    def test_render_prompt_embeds_product_data_as_russian_json(self) -> None:
        prompt = render_prompt(
            title="Ноутбук Lenovo ThinkPad X1",
            category_name="Ноутбуки",
            params={"состояние": "б/у", "Оперативная память": "16 ГБ"},
        )

        self.assertIn("**title:** Ноутбук Lenovo ThinkPad X1", prompt)
        self.assertIn("**category_name:** Ноутбуки", prompt)
        self.assertIn('"состояние": "б/у"', prompt)
        self.assertIn('"Оперативная память": "16 ГБ"', prompt)
        self.assertNotIn("\\u0441", prompt)

    def test_parse_params_json_accepts_empty_value(self) -> None:
        self.assertEqual(parse_params_json(""), {})
        self.assertEqual(parse_params_json(None), {})

    def test_parse_params_json_accepts_object(self) -> None:
        params = parse_params_json(json.dumps({"brand": "Apple", "состояние": "новое"}))

        self.assertEqual(params, {"brand": "Apple", "состояние": "новое"})

    def test_parse_params_json_rejects_non_object(self) -> None:
        with self.assertRaises(ValueError):
            parse_params_json('["not", "a", "dict"]')


if __name__ == "__main__":
    unittest.main()
