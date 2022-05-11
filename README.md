# cloud-panel

A simple Python-based VirtualBox Orchestration system


## Installation \ Установка

```bash
git clone git@github.com:koroteevmv/cloud-panel.git
cd cloud-panel/
python3 -m venv venv-panel
source venv-allocation/bin/activate
pip install -r requirements.txt
python app.py
```

## Usage \ Применение

После развертывания доступно веб-приложение с авторизацией через MS Azure. 

Основные возможности:
* На главной странице отображается список виртуальных машин.
* Каждую машину можно запустить, остановить или удалить. 
* Пользователь видит только свои машины, администратор - любые
* При запуске машине автоматически назначается порт и демонстрируется строка подключения по SSH.

## Future development \ В разработке

* Загрузка пользовательских образов
* Создание образов
* Переход на другой гипервизор
* Страница настроек
* Более подробная документация

## Contributing \ Участие

Пулл-реквесты приветствуются. Для серьезных изменений откройте issue для обсуждения того, что вы хотите поменять.

## License \ Лицензия

[MIT](https://choosealicense.com/licenses/mit/)
