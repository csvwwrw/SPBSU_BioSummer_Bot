# -*- coding: utf-8 -*-

import telebot
from telebot import types
import os
import sqlite3
from sqlite3 import Error
import time
import logging
import sys

sys.tracebacklimit = -1

###   INNITIATING TELEBOT   ###
with open('mountables/token.txt', 'r') as file: # don't forget to create "token.txt" in "biosummer_bot" directory with tg bot token
    TG_TOKEN = file.read().strip()
    
bot = telebot.TeleBot(TG_TOKEN)

###   SETTING UP LOGGER   ###
logging.basicConfig(format = '[%(asctime)s] %(levelname)s: %(message)s',
                    filename = 'mountables/logger.log', 
                    filemode = 'w',
                    encoding = 'utf-8', 
                    level = logging.WARNING)
logging.getLogger().setLevel(logging.INFO)
db_path = 'mountables/voting.db'
max_packs = len([f for f in os.listdir("mountables/entries/") if os.path.isdir(os.path.join("mountables/entries/", f))]) + 1
db_name = 'voting_2024'

# ---------TG BOT COMMANDS--------- #

###   "START"   ###
@bot.message_handler(commands = ['start'])
def start_message(message):
    # just a welcome message
    bot.reply_to(message,
                 """Привет, дорогой студент!
Сейчас тебе предстоит выбрать лучшие фотографии с летней практики этого года. Для этого напиши в чат команду /vote.🌱
Удачи!

Чтобы выбрать фотографию, нажми на кнопку с соответствующим номером ОДИН раз (писать в чат ничего НЕ нужно).
Пожалуйста, будь внимателен при выборе фотографий, так как к предыдущему выбору вернуться нельзя.
Чтобы начать всё голосование заново, напиши /cancel, а затем снова /vote. 🌿""")

###   "VOTE"   ###
@bot.message_handler(commands = ['vote'])
def voting_message(message):
    db_vote_check(message, message.from_user.id) #first bot checks if user's id already exists in db

###   "CANCEL"   ###    
@bot.message_handler(commands = ['cancel'])
def cancel_message(message):
    
    try:
        connection = create_connection(db_path, message) 
        if connection.execute(check_id.format(message.from_user.id)).fetchone() == (1,):
            # if user's id is in db, the whole row is deleated
            execute_query(connection, 
                          db_delete.format(message.from_user.id),
                          message
                          )
            bot.send_message(message.from_user.id,
                             'Готово! Твои голоса удалены. Чтобы проголосовать снова, введи команду /vote.'
                             )
            logging.info(f'Юзер {message.from_user.id} - Данные из базы стёрты.')
        else:
            # if not, nothing happens
            bot.send_message(message.from_user.id,
                             'Кажется, у нас нет твоего голоса. Чтобы сделать это, напиши в чат команду /vote.'
                             )
            logging.info(f'Юзер {message.from_user.id} - Попытка стереть несуществующую запись в базе данных.')
    
    except Error as e:
        exception_message(message)
        logging.warning(f'Юзер {message.from_user.id} - Попытка стереть запись в базе данных неудачна.\n {e}')


# ---------VOTING FUNCTIONS--------- #

### CHECK IF ID IS IN DB  ###
def db_vote_check(message, voter_id):
    try:
        connection = create_connection(db_path, message)
        if connection.execute(check_id.format(voter_id)).fetchone() == (1,):
            # if id is already in db, user is informed and nothing happens
            logging.info(f'Юзер {message.from_user.id} - запрос по первичной проверке успешен.')
            bot.send_message(message.from_user.id, 
                             'Кажется, ты уже голосовал. Если хочешь начать всё голосование заново, напиши /cancel, а затем снова /vote.'
                             )
            logging.info(f'Юзер {message.from_user.id} - Попытка проголосовать неудачна, запись уже есть в базе данных.')
        else:
            # if id is not in db, bot proceeds with voting starting from PACK_1
            vote(message, 1)
            
    except Error as e:
        exception_message(message)
        logging.warning(f'Юзер {message.from_user.id} - Попытка проверить наличие записи в базе данных неудачна.\n{e}')
        
###   SAVING VOTE   ###
def db_add_vote(message, voter_id, pack, image):
    image = image
    pack = pack
    connection = create_connection(db_path, message)
    if connection.execute(check_id.format(voter_id)).fetchone() == (1,):
        #if user presses a button in certain keyboard for the first time
        execute_query(connection, 
                      db_update.format(pack, image, voter_id),
                      message
                      )
        logging.info(f'Юзер {message.from_user.id} - Записан в БД голос за {image} в паке {pack}. [перезапись]')
    else:
        #if user presses a button in certain keyboard after another button was already pressed
        execute_query(connection,
                      db_insert.format(pack, voter_id, image),
                           message)
        logging.info(f'Юзер {message.from_user.id} - Записан в БД голос за {image} в паке {pack}. [новое]')

###   DEALING WITH ENTRIES PACKS  ###
def vote(message, pack):
    images = os.listdir(f'mountables/entries/PACK_{pack}/')
    total_items = len(images)
    # setting up paginated keyboard:
    items_per_page = 60  
    current_page = 1

    try:
        # sending photos from each pack
        for image in images:
            image_num = images.index(image) + 1
            try:
                bot.send_photo(
                    message.from_user.id,
                    open(f'mountables/entries/PACK_{pack}/{image_num}.jpg', 'rb'),
                    caption=str(image_num),
                    parse_mode='HTML'
                )
                time.sleep(0.7)
                
            except Error as e:
                logging.warning(f'Юзер {message.from_user.id} - Ошибка при отправке фото. {e}')
                exception_message(message)

        # creating markup keyboard based on number of max buttons (items_per_page)
        markup = create_pagination_markup(total_items, items_per_page, current_page, pack, message)
        bot.send_message(
            message.from_user.id,
            'Выбери фотографию (используй кнопки "Назад" и "Вперед" для навигации если фотографий больше 60):',
            reply_markup=markup
        )
        logging.info(f'Юзер {message.from_user.id} - Получил голосование по паку {pack}.')
    
    except Error as e:
        exception_message(message)
        logging.warning(f'Юзер {message.from_user.id} - Ошибка при обработке пака {pack}.\n{e}')


###   CREATING PAGINATEG KEYBOARD   ###
def create_pagination_markup(total_items, items_per_page, current_page, pack, message):
    try:
        # determining the range of items for the current page
        start_index = (current_page - 1) * items_per_page
        end_index = min(start_index + items_per_page, total_items)
    
        # creating buttons for the current page
        buttons = [
            types.InlineKeyboardButton(str(i + 1), callback_data=f'{pack}_{i + 1}')
            for i in range(start_index, end_index)
        ]
    
        # adding navigation buttons
        nav_buttons = []
        if current_page > 1:
            nav_buttons.append(types.InlineKeyboardButton('⬅ Назад', callback_data=f'prev_{pack}_{current_page - 1}'))
        if end_index < total_items:
            nav_buttons.append(types.InlineKeyboardButton('Вперед ➡', callback_data=f'next_{pack}_{current_page + 1}'))
    
        # finalizing markup keyboard
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(*buttons)
        if nav_buttons:
            markup.add(*nav_buttons)
    
        return markup
    
    except Error as e:
        exception_message(message)
        logging.warning(f'Юзер {message.from_user.id} - Ошибка при обработке клавиатуры для пака {pack}.\n{e}')



###   HANDLING CALLBACKS FOR NAVIGATION BUTTONS   ###
@bot.callback_query_handler(func=lambda call: call.data.startswith('prev_') or call.data.startswith('next_'))
def handle_navigation(call):
    _, pack, page = call.data.split('_')
    pack = int(pack)
    page = int(page)

    images = os.listdir(f'mountables/entries/PACK_{pack}/')
    total_items = len(images)
    items_per_page = 60

    # create the updated markup for the new page
    markup = create_pagination_markup(total_items, items_per_page, page, pack)
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)


###   HANDLING CALLBACKS FROM VOTING KEYBOARDS   ###
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    try:
        data = call.data.split('_')
        if data[0] in ['prev', 'next']:
            pack = int(data[1])
            page = int(data[2])
            vote(call, pack, page)  # call vote function with the correct page
        else:
            pack = data[0]
            image = data[1]
            db_add_vote(call, call.from_user.id, pack, image)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"Вы выбрали фотографию {image}",
                reply_markup=None
            )
            logging.info(f'Юзер {call.from_user.id} - Проголосовал за картинку {image} в паке {pack}.')
            pack = int(pack) + 1
            if pack != max_packs:
                vote(call, pack)
            else:
                bot.send_message(
                    call.from_user.id,
                    'Готово! Твои голоса учтены! Чтобы перголосовать, введи команду /cancel, а затем снова /vote.'
                )
    except Error as e:
        exception_message(call)
        logging.warning(f'Юзер {call.message.from_user.id} - Ошибка обработки нажатия кнопки. {e}')

        
       
# ---------EXCEPTION MESSAGE FEEDBACK FOR USER--------- #

def exception_message(message):
    bot.send_message(message.from_user.id,
                     'Упс! Что-то пошло не так при обработке твоего запроса. Попробуй ещё раз.')


# ---------DEALING WITH SQL--------- #

###   CONNECTING to DB   ###
def create_connection(path, message):
    connection = None
    try:
        connection = sqlite3.connect(db_path)
        logging.info(f'Юзер {message.from_user.id} - Бот потключился к базе данных.')
    except Error as e:
        logging.warning(f'Юзер {message.from_user.id} - Ошибка при подключении к базе данных. {e}')
        exception_message(message)

    return connection

###   FINALIZING REQUEST   ###
def execute_query(connection, query, message):
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        connection.commit()
        logging.info(f'Юзер {message.from_user.id} - Запрос к базе данныз выполнен успешно.')
    except Error as e:
        logging.warning(f'Юзер {message.from_user.id} - Ошибка при выполнении запроса к базе данных.\n{e}')
        exception_message(message)
        
###   REQUEST LIST   ###
check_id = f'''SELECT EXISTS (SELECT * FROM {db_name} WHERE id = {{}})'''
db_update = f'''UPDATE {db_name} SET pack_{{}} = {{}} WHERE id = {{}}'''
db_delete = f'''DELETE FROM {db_name} WHERE id = {{}}'''
db_insert = f'''INSERT INTO 
     {db_name} (id, pack_{{}}) 
     VALUES ({{}}, {{}})'''


# ---------START BOT POLLING--------- #
bot.infinity_polling(timeout = 120, long_polling_timeout = 120)