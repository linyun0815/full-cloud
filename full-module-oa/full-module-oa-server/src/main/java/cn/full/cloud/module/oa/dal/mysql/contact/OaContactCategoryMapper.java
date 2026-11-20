package cn.full.cloud.module.oa.dal.mysql.contact;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.oa.dal.dataobject.contact.OaContactCategoryDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * OA 联系人分类 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface OaContactCategoryMapper extends BaseMapperX<OaContactCategoryDO> {

    default List<OaContactCategoryDO> selectListByUserId(Long userId) {
        return selectList(new LambdaQueryWrapperX<OaContactCategoryDO>()
                .eq(OaContactCategoryDO::getUserId, userId)
                .orderByAsc(OaContactCategoryDO::getSort)
                .orderByAsc(OaContactCategoryDO::getId));
    }

    default OaContactCategoryDO selectByUserIdAndName(Long userId, String name) {
        return selectOne(OaContactCategoryDO::getUserId, userId, OaContactCategoryDO::getName, name);
    }

}
