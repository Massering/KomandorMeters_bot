import os
from datetime import datetime as dt, timedelta
from time import sleep

import json
from openpyxl import styles, Workbook
import sqlite3
import telebot
from telebot import types

# Имена файлов, использующихся в программе
DB_NAME = "Table.sqlite"
EXCEL_TABLE = "temp_table.xlsx"
USERS_NAME = 'users.json'
COMPANIES_NAME = 'companies.json'

# Константы, по совместительству заголовки в таблице Excel
# Лучше не менять, иначе файл users.json нужно будет перезаписать
HEADERS = ['Company', 'Address', 'Username', 'Phone', 'Counter', 'Data', 'Datetime']
COMPANY, ADDRESS, USERNAME, PHONE, COUNTER, DATA, DATETIME = HEADERS

POSITIVE_ANSWERS = ['yes', 'y', 'да', 'д', '1', 'дп', 'lf']  # Ответы, которые мы принимаем за положительный ответ
RUS = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
ENG = 'abcdefghijklmnopqrstuvwxyz'
DIGITS = '1234567890'
ALLOWED_SIMBOLS = DIGITS + ENG + ENG.upper() + RUS + RUS.upper() + ' -.,()/+_'


def dump(obj, filename):
    """Функция для простого внесения данных в файлы"""
    json.dump(obj, open(filename, 'w', encoding='UTF-8'), ensure_ascii=False, indent=4)


#          Sophia,     Maksim
ADMINS = [979923466, 1089524173]
TOKEN = '5253767532:AAF9DZ2obpuMVKiQD_VHmskA5WTtkjkys3k'

bot = telebot.TeleBot(TOKEN)

# Открытие БД
conn = sqlite3.connect(DB_NAME, check_same_thread=False)

# Создание и открытие json файла со списком зарегистрированных пользователей
if not os.path.exists(USERS_NAME):
    dump({}, USERS_NAME)
users = json.load(open(USERS_NAME, 'r', encoding='utf-8'))

# Создание и открытие файла со списком компаний
if not os.path.exists(COMPANIES_NAME):
    dump({}, COMPANIES_NAME)
companies = json.load(open(COMPANIES_NAME, 'r', encoding='UTF-8'))

# Словарь, в котором будет содержаться информация, которую вносят пользователи в данный момент
recording_data = {}


def get_date():
    """Получение строки с датой и временем сейчас"""
    return dt.now().strftime("%Y-%m-%d %H:%M:%S")


def check_number(number):
    """Изменение номера телефона по формату"""
    number = ''.join(number.replace('(', '').replace(')', '').replace('-', '').split())
    if number[0] == '8':
        number = '+7' + number[1:]
    assert number[1:].isdigit()
    assert len(number) == 12
    assert number[:2] == '+7'
    return number


def check_data(data):
    return data.isdigit() and all(i in '0123456789.' for i in data)


def log(message, symbols=ALLOWED_SIMBOLS):
    """Вывод в консоль уведомления о сообщении боту + Проверка сообщения (выход, атака)"""
    name = message.from_user.username or 'Unknown'
    if str(message.from_user.id) not in users:
        name += f' (id {message.from_user.id})'
    print(f'{get_date()} - {name}: "{message.text}"')

    if message.text == '/exit':
        bot.send_message(message.from_user.id, 'Ок. Выход')
        return 1
    if any(i not in symbols for i in message.text):
        bot.send_message(message.from_user.id, 'Вы ввели что-то неправильно')
        return 1
    if len(message.text) > 255 or not message.text:
        bot.send_message(message.from_user.id, 'Вы ввели что-то неправильно')
        return 1
    return 0


def make_bool_keyboard(one_time=True):
    """Возвращает клавиатуру, состоящую из кнопок "Да" и "Нет\""""
    keyboard = types.ReplyKeyboardMarkup(True, one_time)
    keyboard.add(types.KeyboardButton('Да'), types.KeyboardButton('Нет'))
    return keyboard


def make_keyboard(values, one_time=True):
    """Возвращает клавиатуру, содержащую кнопки со значениями values"""
    keyboard = types.ReplyKeyboardMarkup(True, one_time)
    for value in values:
        key1 = types.KeyboardButton(value)
        keyboard.add(key1)
    return keyboard


@bot.message_handler(content_types=['text'])
def start(message):
    """Изначальная функция, принимающая запросы пользователя"""
    log(message)

    if str(message.from_user.id) not in users:
        bot.send_message(message.from_user.id, "Вы не зарегистрированы. Хотите зарегистрироваться?",
                         reply_markup=make_bool_keyboard())
        bot.register_next_step_handler(message, if_registration)

    elif message.text == '/createentry':
        user = users[str(message.from_user.id)]

        # Предлагаем пользователю список счётчиков по этому адресу
        counters = companies[user[COMPANY]][user[ADDRESS]]

        # Если счетчик всего один, не спрашиваем пользователя
        if len(counters) == 0:
            bot.send_message(message.from_user.id, 'Нет зарегистрированных приборов учёта. '
                                                   'Для регистрации введите /add_counter')
            return

        if len(counters) == 1:
            message.text = list(counters)[0]
            get_counter(message)
            return

        bot.send_message(message.from_user.id, "Выберите номер прибора учёта из списка",
                         reply_markup=make_keyboard(counters))
        bot.register_next_step_handler(message, get_counter)

    elif message.text == '/edit_user':
        if str(message.from_user.id) in users:
            # Подтверждаем регистрацию, если пользователь уже был зарегистрирован
            bot.send_message(message.from_user.id, 'Вы уже зарегистрированы. Ваши данные будут заменены. Вы уверены?',
                             reply_markup=make_bool_keyboard())
            bot.register_next_step_handler(message, if_registration)
        else:
            message.text = 'да'
            if_registration(message)
            return

    elif message.text == '/add_counter':
        bot.send_message(message.from_user.id, 'Введите номер регистрируемого прибора учёта')
        bot.register_next_step_handler(message, add_counter)

    elif message.from_user.id in ADMINS and message.text == '/add_company':
        bot.send_message(message.from_user.id, 'Введите название регистрируемой компании')
        bot.register_next_step_handler(message, add_company)

    elif message.from_user.id in ADMINS and message.text == '/remove_user':
        bot.send_message(message.from_user.id, 'Введите id пользователя')
        bot.register_next_step_handler(message, remove_user_by_id)

    elif message.from_user.id in ADMINS and message.text == '/get_records':
        date_from = dt.now() - timedelta(days=30)
        date_to = dt.now()
        cursor = conn.cursor()
        request = (f"SELECT * FROM records WHERE {DATETIME} BETWEEN '{date_from.strftime('%Y-%m-%d')}'"
                   f" AND '{get_date()}' ORDER BY {DATETIME}")
        result = cursor.execute(request).fetchall()
        cursor.close()

        workbook = Workbook()
        sheet = workbook.worksheets[0]
        for j, header in enumerate(HEADERS, 1):
            cell = sheet.cell(1, j)
            cell.value = header.capitalize()
            cell.font = styles.Font(bold=True)
            cell.alignment = styles.Alignment(horizontal='center')

        for i, record in enumerate(result, 2):
            for j, value in enumerate(record[1:], 1):
                cell = sheet.cell(i, j)
                cell.value = value

        workbook.save(EXCEL_TABLE)
        workbook.close()

        filename = f"Entries for {date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}"
        bot.send_document(message.chat.id, open(EXCEL_TABLE, 'rb').read(),
                          visible_file_name=filename + '.xlsx')
        os.remove(EXCEL_TABLE)

    # Обработка сообщений, не содержащих команд
    else:
        text = f'''Воспользуйтесь функциями меню:
/createentry - для внесения показания прибора учета
/get_entries - для получения записанных показаний по приборам учета
/add_counter - для регистрации прибора учета по вашему адресу
/edit_user - для редактирования вашего профиля
/exit - для завершения работы'''
        if message.from_user.id in ADMINS:
            text += '''\n
/get_records - для получения показаний за месяц в Excel таблице
/add_company - для добавления компании
/get_companies - просмотр всех зарегистрированных компаний
/remove_user - для удаления зарегистрированного пользователя по id'''
        bot.send_message(message.from_user.id, text)


@bot.message_handler(commands=['get_companies'])
def get_companies(message):
    if message.from_user.id not in ADMINS:
        start(message)
        return

    if companies:
        text = 'Список всех зарегистрированных компаний:\n'
        text += '\n'.join(companies)
    else:
        text = 'Нет зарегистрированных компаний'
    bot.send_message(message.from_user.id, text)


@bot.message_handler(commands=['get_entries'])
def get_entries(message):
    user = users[str(message.from_user.id)]
    if companies[user[COMPANY]][user[ADDRESS]]:
        text = 'Внесенные показания по вашим приборам учета:\n'
        text += '\n'.join([f'{i[0]}: {i[1]}' for i in companies[user[COMPANY]][user[ADDRESS]].items()])
    else:
        text = 'Нет зарегистрированных приборов учета'
    bot.send_message(message.from_user.id, text)


def remove_user_by_id(message):
    if log(message):
        return

    if message.text not in users:
        bot.send_message(message.from_user.id, 'Пользователь с этим id не зарегистрирован')
        return

    recording_data[message.from_user.id] = message.text

    data = "\n".join([": ".join(map(str, i)) for i in [('id', message.text)] + list(users[message.text].items())])
    bot.send_message(message.from_user.id, f'Вы действительно хотите удалить пользователя с данными:\n{data}?',
                     reply_markup=make_bool_keyboard())
    bot.register_next_step_handler(message, remove_user_by_id_verification)


def remove_user_by_id_verification(message):
    """Подтверждение регистрации компании"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    if message.text.lower() in POSITIVE_ANSWERS:
        del users[recording_data[message.from_user.id]]
        dump(users, USERS_NAME)

        bot.send_message(int(recording_data[message.from_user.id]), 'Вы были удалены администратором.')
        bot.send_message(message.from_user.id, f'Пользователь {recording_data[message.from_user.id]} удален.')

        del recording_data[message.from_user.id]

    else:
        bot.send_message(message.from_user.id, 'Хорошо')
        message.text = 'exit_code_1'
        start(message)


def add_company(message):
    """Регистрация компании администратором"""
    if log(message):
        return

    recording_data[message.from_user.id] = message.text
    bot.send_message(message.from_user.id, f'Зарегистрировать компанию "{message.text}"?',
                     reply_markup=make_bool_keyboard())
    bot.register_next_step_handler(message, add_company_verification)


def add_company_verification(message):
    """Подтверждение регистрации компании"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    if message.text.lower() in POSITIVE_ANSWERS:
        companies[recording_data[message.from_user.id]] = {}
        dump(companies, COMPANIES_NAME)

        del recording_data[message.from_user.id]

        bot.send_message(message.from_user.id, 'Компания зарегистрирована')

    else:
        bot.send_message(message.from_user.id, 'Хорошо')
        message.text = 'exit_code_1'
        start(message)


def add_counter(message):
    """Регистрация прибора учета пользователем"""
    if log(message):
        return

    recording_data[message.from_user.id] = message.text
    bot.send_message(message.from_user.id, f'Зарегистрировать прибор учета с номером "{message.text}" '
                                           f'по адресу "{users[str(message.from_user.id)][ADDRESS]}"?',
                     reply_markup=make_bool_keyboard())
    bot.register_next_step_handler(message, add_counter_verification)


def add_counter_verification(message):
    """Подтверждение регистрации прибора учета пользователем"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    if message.text.lower() in POSITIVE_ANSWERS:
        user = users[str(message.from_user.id)]
        companies[user[COMPANY]][user[ADDRESS]][recording_data[message.from_user.id]] = ""
        dump(companies, COMPANIES_NAME)

        del recording_data[message.from_user.id]

        bot.send_message(message.from_user.id, 'Прибор учета зарегистрирован')

    else:
        bot.send_message(message.from_user.id, 'Хорошо')
        message.text = 'exit_code_1'
        start(message)


def get_counter(message):
    """Получение названия/номера счётчика у пользователя"""
    if log(message):
        return

    counter = message.text
    user = users[str(message.from_user.id)]
    cur_data = recording_data[message.from_user.id] = user.copy()

    if counter in companies[user[COMPANY]][user[ADDRESS]]:
        value = companies[user[COMPANY]][user[ADDRESS]][counter]
        if value:
            bot.send_message(message.from_user.id, f'Прошлое показание прибора учёта "{counter}": {value}')
        else:
            bot.send_message(message.from_user.id, f'Нет предыдущих показаний по счётчику "{counter}"')

    else:
        bot.send_message(message.from_user.id, 'Прибор учёта с таким номером не зарегистрирован. '
                                               'Для регистрации введите /add_counter')
        return

    cur_data[COUNTER] = message.text

    bot.send_message(message.from_user.id, f'Введите текущее показание прибора учёта с номером "{message.text}"')
    bot.register_next_step_handler(message, get_data)


def get_data(message):
    """Получение данных счётчика у пользователя"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    if check_data(message.text):
        cur_data = recording_data[message.from_user.id]
        cur_data[DATA] = message.text
        cur_data[DATETIME] = get_date()

        s = "\n".join([": ".join(map(str, i)) for i in cur_data.items()])
        bot.send_message(message.from_user.id, f'Полученные данные: \n{s}')
        bot.send_message(message.from_user.id, f'Всё верно?', reply_markup=make_bool_keyboard())
        bot.register_next_step_handler(message, data_verification)

    else:
        bot.send_message(message.from_user.id, f'Введенные данные в неверном формате')
        bot.register_next_step_handler(message, data_verification)


def data_verification(message):
    if log(message):
        del recording_data[message.from_user.id]
        return

    if message.text.lower() not in POSITIVE_ANSWERS:
        del recording_data[message.from_user.id]
        bot.send_message(message.from_user.id, f'Данные не записаны')
        return

    cur_data = recording_data[message.from_user.id]

    companies[cur_data[COMPANY]][cur_data[ADDRESS]][cur_data[COUNTER]] = cur_data[DATA]
    dump(companies, COMPANIES_NAME)

    cursor = conn.cursor()
    # COMPANY, ADDRESS, USERNAME, PHONE, COUNTER, DATA, DATETIME = HEADERS
    cursor.execute(f"INSERT INTO records ({', '.join(HEADERS)}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   list(cur_data.values()))
    cursor.close()
    conn.commit()

    del cur_data

    bot.send_message(message.from_user.id, f'Данные записаны')


def if_registration(message):
    """Проверка, точно ли пользователь хочет зарегистрироваться
    Регистрация происходит в несколько этапов.
    Компания => Номер телефона => Имя
    Эти данные впоследствии будут заноситься в таблицу, когда этот пользователь вводит показания"""
    if log(message):
        return

    if message.text.lower() in POSITIVE_ANSWERS:
        recording_data[message.from_user.id] = {}

        if str(message.from_user.id) in users:
            markup = make_keyboard([users[str(message.from_user.id)][COMPANY]])
        else:
            markup = None

        bot.send_message(message.from_user.id, 'Введите название своей компании',
                         reply_markup=markup)
        bot.register_next_step_handler(message, register_company)

    else:
        bot.send_message(message.from_user.id, 'Ок. Не хотите - не надо')


def register_company(message):
    """Получение компании, в которой работает пользователь"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    if message.text not in companies:
        bot.send_message(message.from_user.id, 'Такой компании нет. Введите ещё раз')
        bot.register_next_step_handler(message, register_company)
        return

    recording_data[message.from_user.id][COMPANY] = message.text

    addresses = companies[message.text]
    bot.send_message(message.from_user.id, 'Выберите адрес своего магазина из списка или, '
                                           'если его нет, введите вручную',
                     reply_markup=make_keyboard(addresses))
    bot.register_next_step_handler(message, register_address)


def register_address(message):
    """Получение адреса, по которому работает пользователь"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    recording_data[message.from_user.id][ADDRESS] = message.text

    if str(message.from_user.id) in users:
        markup = make_keyboard([users[str(message.from_user.id)][PHONE]], False)
    else:
        markup = None

    bot.send_message(message.from_user.id, 'Введите свой номер телефона в федеральном формате (+7**********)',
                     reply_markup=markup)
    bot.register_next_step_handler(message, register_phone)


def register_phone(message):
    """Получение номера телефона пользователя"""
    if log(message, '+1234567890'):
        del recording_data[message.from_user.id]
        return

    try:
        recording_data[message.from_user.id][PHONE] = check_number(message.text)

        # Предлагаем ему имя, под которым он зарегистрирован в Телеграмме
        # и также имя, под которым он был зарегистрирован в прошлый раз
        names = [((message.from_user.last_name or ' ') + ' ' + (message.from_user.first_name or ' ')).strip()]
        if str(message.from_user.id) in users and users[str(message.from_user.id)][USERNAME] != names[0]:
            names.insert(0, users[str(message.from_user.id)][USERNAME])

        bot.send_message(message.from_user.id, 'Введите своё имя', reply_markup=make_keyboard(names, False))
        bot.register_next_step_handler(message, register_name)

    except (AssertionError, IndexError, ValueError):
        bot.send_message(message.from_user.id, 'Номер введён неправильно. Введите ещё раз')
        bot.register_next_step_handler(message, register_phone)


def register_name(message):
    """Получение имени пользователя"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    recording_data[message.from_user.id][USERNAME] = message.text

    s = "\n".join([": ".join(i) for i in recording_data[message.from_user.id].items()])
    bot.send_message(message.from_user.id, f'Ваши данные: \n{s}')
    bot.send_message(message.from_user.id, f'Внести их?', reply_markup=make_bool_keyboard())
    bot.register_next_step_handler(message, register_verification)


def register_verification(message):
    """Подтверждение внесения данных у пользователя"""
    if log(message):
        del recording_data[message.from_user.id]
        return

    user_id = message.from_user.id
    cur_data = recording_data[user_id]

    if message.text.lower() in POSITIVE_ANSWERS:
        if cur_data[ADDRESS] not in companies[cur_data[COMPANY]]:
            companies[cur_data[COMPANY]][cur_data[ADDRESS]] = {}
            dump(companies, COMPANIES_NAME)

        users[str(user_id)] = cur_data.copy()
        # Перезапись файла
        dump(users, USERS_NAME)
        del cur_data

        bot.send_message(user_id, 'Вы успешно зарегистрированы!')

        # Отправляем админу информацию о регистрации
        s = "\n".join([": ".join(i) for i in users[str(user_id)].items()])
        for admin in ADMINS:
            bot.send_message(admin, f'Пользователь\nid: {user_id}\n{s}\nЗарегистрировался')
    else:
        del cur_data
        bot.send_message(user_id, f'Регистрация отменена')


if __name__ == "__main__":
    while 1:
        try:
            bot.polling(none_stop=True, interval=0)
        except Exception as error:
            print(f'{get_date()} - FATAL_ERROR({error.__class__}, {error.__cause__}): {error}')
            sleep(1)
