from byubit import Bit

@Bit.worlds('t')
# @Bit.pictures('demo-images/', ext='png')
def main(bit):
    bit.paint('red')
    while bit.front_clear():
        bit.move()
        bit.paint('#33E5B4')
    bit.paint('#444222')
    # print(bit.get_color())
    # bit._image('./demo-images/90_2.jpeg')
    bit.bean()

if __name__ == '__main__':
    main(Bit.new_bit)
